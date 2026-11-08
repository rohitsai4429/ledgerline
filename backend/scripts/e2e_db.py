from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import case, create_engine, func, select, text
from sqlalchemy.engine import Connection, URL, make_url
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_migration_database_url, get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.account import (  # noqa: E402
    Account,
    AccountStatus,
    LedgerAccount,
    LedgerAccountKind,
)
from app.models.transaction import (  # noqa: E402
    AuditEvent,
    IdempotencyRecord,
    JournalTransaction,
    JournalTransactionStatus,
    JournalTransactionType,
    LedgerEntry,
    LedgerEntryType,
)
from app.models.user import User, UserRole, UserStatus  # noqa: E402

SCHEMA_PATTERN = re.compile(r"ledgerline_e2e_[0-9a-f]{12}")
TEST_PASSWORD_ENV = "E2E_TEST_PASSWORD"


def _validate_schema(schema: str) -> None:
    if not SCHEMA_PATTERN.fullmatch(schema):
        raise ValueError("Refusing to use a schema outside the generated E2E namespace")


def _quote_schema(schema: str) -> str:
    _validate_schema(schema)
    return f'"{schema}"'


def _validate_run(schema: str, suffix: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{12}", suffix) or schema != f"ledgerline_e2e_{suffix}":
        raise ValueError("The schema must match this generated E2E run")


def _schema_marker(suffix: str) -> str:
    return f"ledgerline-e2e-run:{suffix}"


def _drop_owned_schema(connection: Connection, schema: str, suffix: str) -> None:
    marker = connection.scalar(
        text(
            "SELECT obj_description(oid, 'pg_namespace') "
            "FROM pg_namespace WHERE nspname = :schema"
        ),
        {"schema": schema},
    )
    if marker != _schema_marker(suffix):
        raise RuntimeError("Refusing to remove a schema not created by this E2E run")
    connection.execute(text(f"DROP SCHEMA {_quote_schema(schema)} CASCADE"))


def _urls() -> tuple[URL, URL]:
    migration_url_string = get_migration_database_url()
    if migration_url_string is None:
        raise RuntimeError("MIGRATION_DATABASE_URL must be configured in backend/.env")
    migration_url = make_url(migration_url_string)
    runtime_url = make_url(get_settings().database_url)
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if migration_url.get_backend_name() != "postgresql" or runtime_url.get_backend_name() != "postgresql":
        raise RuntimeError("E2E tests require PostgreSQL URLs")
    if (
        migration_url.host not in local_hosts
        or runtime_url.host not in local_hosts
        or migration_url.host != runtime_url.host
        or (migration_url.port or 5432) != (runtime_url.port or 5432)
        or migration_url.database != runtime_url.database
    ):
        raise RuntimeError("E2E migration and runtime URLs must target the same PostgreSQL database")
    return migration_url, runtime_url


def _schema_engine(url: URL, schema: str):
    return create_engine(
        url,
        connect_args={"options": f"-csearch_path={_validate_and_return(schema)}"},
        pool_pre_ping=True,
    )


def _validate_and_return(schema: str) -> str:
    _validate_schema(schema)
    return schema


def setup(schema: str, suffix: str) -> None:
    _validate_run(schema, suffix)
    quoted_schema = _quote_schema(schema)
    migration_url, runtime_url = _urls()
    password = os.environ.get(TEST_PASSWORD_ENV)
    if not password or len(password) < 12:
        raise RuntimeError(f"{TEST_PASSWORD_ENV} must be provided by Playwright setup")

    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
    schema_created = False
    try:
        with migration_engine.begin() as connection:
            if connection.scalar(text("SELECT current_user")) == "ledgerline_app":
                raise RuntimeError(
                    "MIGRATION_DATABASE_URL must use the privileged schema owner, "
                    "not ledgerline_app"
                )
            if connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
                {"schema": schema},
            ):
                raise RuntimeError("Generated E2E schema unexpectedly already exists")
            if not connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ledgerline_app')")
            ):
                raise RuntimeError("PostgreSQL runtime role ledgerline_app is not provisioned")
            connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
            connection.execute(
                text(f"COMMENT ON SCHEMA {quoted_schema} IS '{_schema_marker(suffix)}'")
            )
            connection.execute(text(f"GRANT USAGE ON SCHEMA {quoted_schema} TO ledgerline_app"))
        schema_created = True

        migration_schema_engine = _schema_engine(migration_url, schema)
        try:
            config = Config(str(BACKEND_ROOT / "alembic.ini"))
            with migration_schema_engine.connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                connection.commit()

            factory = sessionmaker(
                bind=migration_schema_engine,
                autoflush=False,
                expire_on_commit=False,
            )
            with factory() as session:
                for role, email in (
                    (UserRole.ADMIN, f"admin-e2e-{suffix}@example.com"),
                    (UserRole.AUDITOR, f"auditor-e2e-{suffix}@example.com"),
                ):
                    session.add(
                        User(
                            email=email,
                            password_hash=hash_password(password),
                            role=role,
                            status=UserStatus.ACTIVE,
                        )
                    )
                session.commit()
        finally:
            migration_schema_engine.dispose()

        with runtime_engine.connect() as connection:
            if connection.scalar(text("SELECT current_user")) != "ledgerline_app":
                raise RuntimeError("DATABASE_URL must use ledgerline_app")
    except Exception:
        if schema_created:
            with migration_engine.begin() as connection:
                _drop_owned_schema(connection, schema, suffix)
        raise
    finally:
        runtime_engine.dispose()
        migration_engine.dispose()

    print(f"Prepared isolated PostgreSQL schema {schema} at Alembic head.")


def _runtime_engine(schema: str):
    _, runtime_url = _urls()
    return _schema_engine(runtime_url, schema)


def verify(schema: str, suffix: str) -> None:
    _validate_run(schema, suffix)
    engine = _runtime_engine(schema)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with factory() as session:
            customer_a = session.scalar(
                select(User).where(User.email == f"customer-a-{suffix}@example.com")
            )
            customer_b = session.scalar(
                select(User).where(User.email == f"customer-b-{suffix}@example.com")
            )
            assert customer_a is not None and customer_b is not None
            account_a = session.scalar(select(Account).where(Account.owner_user_id == customer_a.id))
            account_b = session.scalar(select(Account).where(Account.owner_user_id == customer_b.id))
            assert account_a is not None and account_b is not None
            assert account_a.status is AccountStatus.ACTIVE
            assert account_b.status is AccountStatus.FROZEN
            assert account_a.balance_paise == 9_000
            assert account_b.balance_paise == 0

            transactions = list(session.scalars(select(JournalTransaction)).all())
            expected_counts = {
                JournalTransactionType.DEPOSIT: 1,
                JournalTransactionType.WITHDRAWAL: 1,
                JournalTransactionType.TRANSFER: 1,
                JournalTransactionType.REVERSAL: 1,
            }
            assert len(transactions) == 4, f"Unexpected transaction count: {len(transactions)}"
            entries_by_transaction: dict[UUID, list[LedgerEntry]] = {}
            for kind, expected in expected_counts.items():
                assert sum(transaction.transaction_type is kind for transaction in transactions) == expected

            for transaction in transactions:
                assert transaction.status is JournalTransactionStatus.POSTED
                entries = list(
                    session.scalars(
                        select(LedgerEntry).where(
                            LedgerEntry.journal_transaction_id == transaction.id
                        )
                    ).all()
                )
                debits = sum(
                    entry.amount_paise
                    for entry in entries
                    if entry.entry_type is LedgerEntryType.DEBIT
                )
                credits = sum(
                    entry.amount_paise
                    for entry in entries
                    if entry.entry_type is LedgerEntryType.CREDIT
                )
                assert len(entries) == 2
                assert debits == credits == transaction.amount_paise
                entries_by_transaction[transaction.id] = entries

            transfer = next(
                transaction
                for transaction in transactions
                if transaction.transaction_type is JournalTransactionType.TRANSFER
            )
            assert transfer.source_account_id == account_a.id
            assert transfer.destination_account_id == account_b.id
            assert transfer.amount_paise == 2_500
            transfer_entries = entries_by_transaction[transfer.id]
            assert {
                (entry.ledger_account_id, entry.entry_type, entry.amount_paise)
                for entry in transfer_entries
            } == {
                (account_a.ledger_account_id, LedgerEntryType.DEBIT, 2_500),
                (account_b.ledger_account_id, LedgerEntryType.CREDIT, 2_500),
            }
            reversal = next(
                transaction
                for transaction in transactions
                if transaction.transaction_type is JournalTransactionType.REVERSAL
            )
            assert reversal.related_transaction_id == transfer.id
            reversed_lines = {
                (
                    entry.ledger_account_id,
                    LedgerEntryType.DEBIT
                    if entry.entry_type is LedgerEntryType.CREDIT
                    else LedgerEntryType.CREDIT,
                    entry.amount_paise,
                )
                for entry in entries_by_transaction[transfer.id]
            }
            reversal_lines = {
                (entry.ledger_account_id, entry.entry_type, entry.amount_paise)
                for entry in entries_by_transaction[reversal.id]
            }
            assert reversal_lines == reversed_lines

            clearing_accounts = {
                account.kind: account.id
                for account in session.scalars(
                    select(LedgerAccount).where(
                        LedgerAccount.kind.in_(
                            [
                                LedgerAccountKind.DEPOSIT_CLEARING,
                                LedgerAccountKind.WITHDRAWAL_CLEARING,
                            ]
                        )
                    )
                ).all()
            }
            deposit = next(
                transaction
                for transaction in transactions
                if transaction.transaction_type is JournalTransactionType.DEPOSIT
            )
            withdrawal = next(
                transaction
                for transaction in transactions
                if transaction.transaction_type is JournalTransactionType.WITHDRAWAL
            )
            assert {
                (entry.ledger_account_id, entry.entry_type, entry.amount_paise)
                for entry in entries_by_transaction[deposit.id]
            } == {
                (clearing_accounts[LedgerAccountKind.DEPOSIT_CLEARING], LedgerEntryType.DEBIT, 10_000),
                (account_a.ledger_account_id, LedgerEntryType.CREDIT, 10_000),
            }
            assert {
                (entry.ledger_account_id, entry.entry_type, entry.amount_paise)
                for entry in entries_by_transaction[withdrawal.id]
            } == {
                (account_a.ledger_account_id, LedgerEntryType.DEBIT, 1_000),
                (clearing_accounts[LedgerAccountKind.WITHDRAWAL_CLEARING], LedgerEntryType.CREDIT, 1_000),
            }

            for account in (account_a, account_b):
                net_ledger_balance = session.scalar(
                    select(
                        func.coalesce(
                            func.sum(
                                case(
                                    (LedgerEntry.entry_type == LedgerEntryType.CREDIT, LedgerEntry.amount_paise),
                                    else_=-LedgerEntry.amount_paise,
                                )
                            ),
                            0,
                        )
                    )
                    .select_from(LedgerEntry)
                    .join(
                        JournalTransaction,
                        JournalTransaction.id == LedgerEntry.journal_transaction_id,
                    )
                    .where(
                        LedgerEntry.ledger_account_id == account.ledger_account_id,
                        JournalTransaction.status == JournalTransactionStatus.POSTED,
                    )
                )
                assert net_ledger_balance == account.balance_paise

            idempotency_count = session.scalar(select(func.count()).select_from(IdempotencyRecord))
            assert idempotency_count >= 9, f"Expected recorded successful and rejected requests, got {idempotency_count}"
            assert session.scalar(
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(IdempotencyRecord.journal_transaction_id == deposit.id)
            ) == 1
            audit_events = list(session.scalars(select(AuditEvent)).all())
            audit_types = {event.event_type for event in audit_events}
            assert "ACCOUNT_STATUS_CHANGED" in audit_types
            assert "REVERSAL" in audit_types
            assert "WITHDRAWAL_REJECTED" in audit_types
            assert any(
                event.event_type == "REVERSAL"
                and event.outcome == "SUCCEEDED"
                and event.journal_transaction_id == reversal.id
                for event in audit_events
            )
    finally:
        engine.dispose()

    print("PostgreSQL journey invariants verified: 4 posted journals, balanced entries, balances reconciled, audit and idempotency records present.")


def cleanup(schema: str, suffix: str) -> None:
    _validate_run(schema, suffix)
    quoted_schema = _quote_schema(schema)
    migration_url, _ = _urls()
    engine = create_engine(migration_url, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            _drop_owned_schema(connection, schema, suffix)
    finally:
        engine.dispose()
    print(f"Removed only isolated E2E schema {schema}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "verify", "cleanup"))
    parser.add_argument("schema")
    parser.add_argument("suffix", nargs="?")
    args = parser.parse_args()
    _validate_schema(args.schema)
    if args.action == "setup":
        if args.suffix is None or not re.fullmatch(r"[0-9a-f]{12}", args.suffix):
            raise ValueError("A generated 12-character hexadecimal run suffix is required")
        setup(args.schema, args.suffix)
    elif args.action == "verify":
        if args.suffix is None or not re.fullmatch(r"[0-9a-f]{12}", args.suffix):
            raise ValueError("A generated 12-character hexadecimal run suffix is required")
        verify(args.schema, args.suffix)
    else:
        if args.suffix is None or not re.fullmatch(r"[0-9a-f]{12}", args.suffix):
            raise ValueError("The exact generated 12-character hexadecimal run suffix is required")
        cleanup(args.schema, args.suffix)


if __name__ == "__main__":
    main()
