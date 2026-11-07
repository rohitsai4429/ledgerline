import hashlib
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.account import Account, AccountStatus, LedgerAccount, LedgerAccountKind
from app.models.transaction import (
    AuditEvent,
    IdempotencyOutcome,
    IdempotencyRecord,
    JournalTransaction,
    JournalTransactionStatus,
    JournalTransactionType,
    LedgerEntry,
    LedgerEntryType,
)
from app.models.user import User, UserRole
from app.repositories.transactions import list_audit_events, list_transactions
from app.schemas.transaction import AccountStatementResponse, StatementEntry
from app.services.audit import add_audit_event

MAX_BALANCE_PAISE = 9_223_372_036_854_775_807
IDEMPOTENCY_REJECTIONS = {
    "permission_denied": (403, "Insufficient permissions"),
    "account_not_found": (404, "Account not found"),
    "transaction_not_found": (404, "Transaction not found"),
    "account_not_active": (409, "Account is not active"),
    "insufficient_funds": (409, "Insufficient funds"),
    "same_account": (422, "Source and destination accounts must differ"),
    "already_reversed": (409, "Transaction has already been reversed"),
    "reversal_not_allowed": (409, "This transaction cannot be reversed"),
    "balance_limit_exceeded": (409, "Account balance limit would be exceeded"),
}


class IdempotencyConflict(Exception):
    pass


class TransactionRejected(Exception):
    def __init__(self, code: str, *, replayed: bool = False) -> None:
        self.code = code
        self.replayed = replayed
        self.status_code, self.detail = IDEMPOTENCY_REJECTIONS.get(
            code,
            (409, "Transaction was rejected"),
        )
        super().__init__(self.detail)


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _advisory_lock_id(user_id: UUID, idempotency_key: str) -> int:
    digest = hashlib.sha256(f"{user_id}:{idempotency_key}".encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


def _add_audit_event(
    db: Session,
    actor: User,
    event_type: str,
    outcome: str,
    details: dict[str, Any],
    journal_transaction_id: UUID | None = None,
) -> None:
    add_audit_event(
        db,
        actor_user_id=actor.id,
        event_type=event_type,
        outcome=outcome,
        details=details,
        journal_transaction_id=journal_transaction_id,
    )


def _execute_idempotently(
    db: Session,
    actor: User,
    idempotency_key: str,
    payload: dict[str, Any],
    event_type: str,
    operation: Callable[[], JournalTransaction],
) -> JournalTransaction:
    payload_hash = _request_hash(payload)
    db.execute(
        select(func.pg_advisory_xact_lock(_advisory_lock_id(actor.id, idempotency_key)))
    )
    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == actor.id,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != payload_hash:
            _add_audit_event(
                db,
                actor,
                f"{event_type}_REJECTED",
                "REJECTED",
                {"reason": "idempotency_payload_mismatch"},
            )
            db.commit()
            raise IdempotencyConflict
        if existing.outcome is IdempotencyOutcome.REJECTED:
            raise TransactionRejected(existing.result_code or "transaction_rejected", replayed=True)
        transaction = db.get(JournalTransaction, existing.journal_transaction_id)
        if transaction is None:
            raise RuntimeError("Successful idempotency record has no transaction")
        return transaction

    try:
        with db.begin_nested():
            transaction = operation()
            record = IdempotencyRecord(
                user_id=actor.id,
                idempotency_key=idempotency_key,
                request_hash=payload_hash,
                outcome=IdempotencyOutcome.SUCCEEDED,
                journal_transaction_id=transaction.id,
            )
            db.add(record)
            _add_audit_event(
                db,
                actor,
                event_type,
                "SUCCEEDED",
                payload,
                transaction.id,
            )
            db.flush()
        db.commit()
        return transaction
    except TransactionRejected as error:
        db.add(
            IdempotencyRecord(
                user_id=actor.id,
                idempotency_key=idempotency_key,
                request_hash=payload_hash,
                outcome=IdempotencyOutcome.REJECTED,
                result_code=error.code,
            )
        )
        _add_audit_event(
            db,
            actor,
            f"{event_type}_REJECTED",
            "REJECTED",
            {**payload, "reason": error.code},
        )
        db.commit()
        raise
    except Exception:
        db.rollback()
        audit_session = Session(
            bind=db.get_bind(),
            autoflush=False,
            expire_on_commit=False,
        )
        try:
            _add_audit_event(
                audit_session,
                actor,
                f"{event_type}_REJECTED",
                "REJECTED",
                {**payload, "reason": "internal_error"},
            )
            audit_session.commit()
        finally:
            audit_session.close()
        raise


def _lock_accounts(db: Session, account_ids: set[UUID]) -> dict[UUID, Account]:
    if not account_ids:
        return {}
    accounts = db.scalars(
        select(Account)
        .where(Account.id.in_(account_ids))
        .order_by(Account.id)
        .with_for_update()
    ).all()
    return {account.id: account for account in accounts}


def _require_account_holder(actor: User) -> None:
    if actor.role is not UserRole.ACCOUNT_HOLDER:
        raise TransactionRejected("permission_denied")


def _require_active(account: Account) -> None:
    if account.status is not AccountStatus.ACTIVE:
        raise TransactionRejected("account_not_active")


def _get_clearing_account(db: Session, kind: LedgerAccountKind) -> LedgerAccount:
    code = {
        LedgerAccountKind.DEPOSIT_CLEARING: "deposit-clearing-inr",
        LedgerAccountKind.WITHDRAWAL_CLEARING: "withdrawal-clearing-inr",
    }[kind]
    account = db.scalar(select(LedgerAccount).where(LedgerAccount.system_code == code))
    if account is None:
        raise RuntimeError(f"Required clearing ledger account is missing: {code}")
    return account


def _create_posted_journal(
    db: Session,
    actor: User,
    transaction_type: JournalTransactionType,
    amount_paise: int,
    source_account_id: UUID | None,
    destination_account_id: UUID | None,
    entries: list[tuple[UUID, LedgerEntryType]],
    related_transaction_id: UUID | None = None,
) -> JournalTransaction:
    transaction = JournalTransaction(
        transaction_type=transaction_type,
        amount_paise=amount_paise,
        source_account_id=source_account_id,
        destination_account_id=destination_account_id,
        related_transaction_id=related_transaction_id,
        initiated_by_user_id=actor.id,
    )
    db.add(transaction)
    db.flush()
    db.add_all(
        [
            LedgerEntry(
                journal_transaction_id=transaction.id,
                ledger_account_id=ledger_account_id,
                entry_type=entry_type,
                amount_paise=amount_paise,
            )
            for ledger_account_id, entry_type in entries
        ]
    )
    db.flush()
    db.execute(
        select(func.ledgerline_mark_journal_posted(transaction.id))
    )
    db.refresh(transaction, attribute_names=["status"])
    return transaction


def deposit(
    db: Session,
    actor: User,
    account_id: UUID,
    amount_paise: int,
    idempotency_key: str,
) -> JournalTransaction:
    payload = {
        "operation": "DEPOSIT",
        "account_id": str(account_id),
        "amount_paise": amount_paise,
        "currency": "INR",
    }

    def post() -> JournalTransaction:
        _require_account_holder(actor)
        accounts = _lock_accounts(db, {account_id})
        account = accounts.get(account_id)
        if account is None or account.owner_user_id != actor.id:
            raise TransactionRejected("account_not_found")
        _require_active(account)
        if account.balance_paise > MAX_BALANCE_PAISE - amount_paise:
            raise TransactionRejected("balance_limit_exceeded")
        clearing = _get_clearing_account(db, LedgerAccountKind.DEPOSIT_CLEARING)
        account.balance_paise += amount_paise
        return _create_posted_journal(
            db,
            actor,
            JournalTransactionType.DEPOSIT,
            amount_paise,
            None,
            account.id,
            [
                (clearing.id, LedgerEntryType.DEBIT),
                (account.ledger_account_id, LedgerEntryType.CREDIT),
            ],
        )

    return _execute_idempotently(
        db,
        actor,
        idempotency_key,
        payload,
        "DEPOSIT",
        post,
    )


def withdraw(
    db: Session,
    actor: User,
    account_id: UUID,
    amount_paise: int,
    idempotency_key: str,
) -> JournalTransaction:
    payload = {
        "operation": "WITHDRAWAL",
        "account_id": str(account_id),
        "amount_paise": amount_paise,
        "currency": "INR",
    }

    def post() -> JournalTransaction:
        _require_account_holder(actor)
        account = _lock_accounts(db, {account_id}).get(account_id)
        if account is None or account.owner_user_id != actor.id:
            raise TransactionRejected("account_not_found")
        _require_active(account)
        if account.balance_paise < amount_paise:
            raise TransactionRejected("insufficient_funds")
        clearing = _get_clearing_account(db, LedgerAccountKind.WITHDRAWAL_CLEARING)
        account.balance_paise -= amount_paise
        return _create_posted_journal(
            db,
            actor,
            JournalTransactionType.WITHDRAWAL,
            amount_paise,
            account.id,
            None,
            [
                (account.ledger_account_id, LedgerEntryType.DEBIT),
                (clearing.id, LedgerEntryType.CREDIT),
            ],
        )

    return _execute_idempotently(
        db,
        actor,
        idempotency_key,
        payload,
        "WITHDRAWAL",
        post,
    )


def transfer(
    db: Session,
    actor: User,
    source_account_id: UUID,
    destination_account_id: UUID,
    amount_paise: int,
    idempotency_key: str,
) -> JournalTransaction:
    payload = {
        "operation": "TRANSFER",
        "source_account_id": str(source_account_id),
        "destination_account_id": str(destination_account_id),
        "amount_paise": amount_paise,
        "currency": "INR",
    }

    def post() -> JournalTransaction:
        _require_account_holder(actor)
        if source_account_id == destination_account_id:
            raise TransactionRejected("same_account")
        accounts = _lock_accounts(db, {source_account_id, destination_account_id})
        source = accounts.get(source_account_id)
        destination = accounts.get(destination_account_id)
        if source is None or source.owner_user_id != actor.id or destination is None:
            raise TransactionRejected("account_not_found")
        _require_active(source)
        _require_active(destination)
        if source.balance_paise < amount_paise:
            raise TransactionRejected("insufficient_funds")
        if destination.balance_paise > MAX_BALANCE_PAISE - amount_paise:
            raise TransactionRejected("balance_limit_exceeded")
        source.balance_paise -= amount_paise
        destination.balance_paise += amount_paise
        return _create_posted_journal(
            db,
            actor,
            JournalTransactionType.TRANSFER,
            amount_paise,
            source.id,
            destination.id,
            [
                (source.ledger_account_id, LedgerEntryType.DEBIT),
                (destination.ledger_account_id, LedgerEntryType.CREDIT),
            ],
        )

    return _execute_idempotently(
        db,
        actor,
        idempotency_key,
        payload,
        "TRANSFER",
        post,
    )


def reverse_transaction(
    db: Session,
    actor: User,
    transaction_id: UUID,
    idempotency_key: str,
) -> JournalTransaction:
    payload = {
        "operation": "REVERSAL",
        "transaction_id": str(transaction_id),
        "currency": "INR",
    }

    def post() -> JournalTransaction:
        if actor.role is not UserRole.ADMIN:
            raise TransactionRejected("permission_denied")
        db.execute(
            select(func.ledgerline_lock_journal_for_reversal(transaction_id))
        )
        original = db.get(JournalTransaction, transaction_id)
        if original is None:
            raise TransactionRejected("transaction_not_found")
        if (
            original.status is not JournalTransactionStatus.POSTED
            or original.transaction_type is JournalTransactionType.REVERSAL
        ):
            raise TransactionRejected("reversal_not_allowed")
        if db.scalar(
            select(JournalTransaction.id).where(
                JournalTransaction.related_transaction_id == original.id
            )
        ) is not None:
            raise TransactionRejected("already_reversed")

        original_entries = list(
            db.scalars(
                select(LedgerEntry).where(
                    LedgerEntry.journal_transaction_id == original.id
                )
            ).all()
        )
        ledger_ids = {entry.ledger_account_id for entry in original_entries}
        accounts_by_ledger = {
            account.ledger_account_id: account
            for account in db.scalars(
                select(Account)
                .where(Account.ledger_account_id.in_(ledger_ids))
                .order_by(Account.id)
                .with_for_update()
            ).all()
        }
        for entry in original_entries:
            account = accounts_by_ledger.get(entry.ledger_account_id)
            if account is None:
                continue
            if entry.entry_type is LedgerEntryType.CREDIT:
                if account.balance_paise < entry.amount_paise:
                    raise TransactionRejected("insufficient_funds")
                account.balance_paise -= entry.amount_paise
            else:
                if account.balance_paise > MAX_BALANCE_PAISE - entry.amount_paise:
                    raise TransactionRejected("balance_limit_exceeded")
                account.balance_paise += entry.amount_paise

        reverse_entries = [
            (
                entry.ledger_account_id,
                LedgerEntryType.DEBIT
                if entry.entry_type is LedgerEntryType.CREDIT
                else LedgerEntryType.CREDIT,
            )
            for entry in original_entries
        ]
        return _create_posted_journal(
            db,
            actor,
            JournalTransactionType.REVERSAL,
            original.amount_paise,
            original.source_account_id,
            original.destination_account_id,
            reverse_entries,
            original.id,
        )

    return _execute_idempotently(
        db,
        actor,
        idempotency_key,
        payload,
        "REVERSAL",
        post,
    )


def get_transaction_history(
    db: Session,
    viewer: User,
    account_id: UUID | None,
    limit: int,
    offset: int,
) -> list[JournalTransaction]:
    account_ids: list[UUID] | None = None
    if viewer.role is UserRole.ACCOUNT_HOLDER:
        account_statement = select(Account.id).where(Account.owner_user_id == viewer.id)
        if account_id is not None:
            account_statement = account_statement.where(Account.id == account_id)
            if db.scalar(account_statement) is None:
                raise TransactionRejected("account_not_found")
        account_ids = list(db.scalars(account_statement).all())
    elif account_id is not None:
        if db.scalar(select(Account.id).where(Account.id == account_id)) is None:
            raise TransactionRejected("account_not_found")
        account_ids = [account_id]
    return list_transactions(db, account_ids, limit, offset)


def get_account_statement(
    db: Session,
    viewer: User,
    account_id: UUID,
    start: datetime | None,
    end: datetime | None,
) -> AccountStatementResponse:
    account = db.get(Account, account_id)
    if account is None or (
        viewer.role is UserRole.ACCOUNT_HOLDER and account.owner_user_id != viewer.id
    ):
        raise TransactionRejected("account_not_found")
    if start is not None and end is not None and start >= end:
        raise ValueError("Statement start must be earlier than end")

    impact = case(
        (LedgerEntry.entry_type == LedgerEntryType.CREDIT, LedgerEntry.amount_paise),
        else_=-LedgerEntry.amount_paise,
    )
    opening = 0
    if start is not None:
        opening = db.scalar(
            select(func.coalesce(func.sum(impact), 0))
            .select_from(LedgerEntry)
            .join(JournalTransaction)
            .where(
                LedgerEntry.ledger_account_id == account.ledger_account_id,
                JournalTransaction.status == JournalTransactionStatus.POSTED,
                JournalTransaction.created_at < start,
            )
        ) or 0

    statement = (
        select(LedgerEntry, JournalTransaction)
        .join(
            JournalTransaction,
            LedgerEntry.journal_transaction_id == JournalTransaction.id,
        )
        .where(
            LedgerEntry.ledger_account_id == account.ledger_account_id,
            JournalTransaction.status == JournalTransactionStatus.POSTED,
        )
    )
    if start is not None:
        statement = statement.where(JournalTransaction.created_at >= start)
    if end is not None:
        statement = statement.where(JournalTransaction.created_at <= end)
    statement = statement.order_by(
        JournalTransaction.created_at,
        JournalTransaction.id,
        LedgerEntry.id,
    )
    rows = db.execute(statement).all()

    balance = opening
    entries: list[StatementEntry] = []
    for ledger_entry, transaction in rows:
        if ledger_entry.entry_type is LedgerEntryType.CREDIT:
            balance += ledger_entry.amount_paise
        else:
            balance -= ledger_entry.amount_paise
        entries.append(
            StatementEntry(
                transaction_id=transaction.id,
                transaction_type=transaction.transaction_type,
                related_transaction_id=transaction.related_transaction_id,
                created_at=transaction.created_at,
                entry_type=ledger_entry.entry_type,
                amount_paise=ledger_entry.amount_paise,
                balance_after_paise=balance,
            )
        )
    return AccountStatementResponse(
        account_id=account.id,
        currency="INR",
        opening_balance_paise=opening,
        closing_balance_paise=balance,
        entries=entries,
    )


def get_audit_history(
    db: Session,
    viewer: User,
    actor_user_id: UUID | None,
    start: datetime | None,
    limit: int,
    offset: int,
) -> list[AuditEvent]:
    if viewer.role not in (UserRole.ADMIN, UserRole.AUDITOR):
        raise TransactionRejected("permission_denied")
    return list_audit_events(db, actor_user_id, start, limit, offset)
