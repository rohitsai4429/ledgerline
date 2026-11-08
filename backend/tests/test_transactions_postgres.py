from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import case, create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_migration_database_url, get_settings
from app.core.security import create_access_token, hash_password
from app.database.session import get_db
from app.main import app
from app.models.account import Account, LedgerAccount, LedgerAccountKind
from app.models.transaction import (
    AuditEvent,
    IdempotencyRecord,
    JournalTransaction,
    JournalTransactionStatus,
    JournalTransactionType,
    LedgerEntry,
    LedgerEntryType,
)
from app.models.user import User, UserRole, UserStatus
from app.schemas.transaction import MAX_AMOUNT_PAISE
from app.services import transactions as transaction_service

_setup_factories: dict[str, sessionmaker[Session]] = {}


@pytest.fixture(scope="module")
def transaction_factory() -> Iterator[sessionmaker[Session]]:
    schema = f"ledgerline_test_{uuid4().hex}"
    settings = get_settings()
    migration_url = get_migration_database_url()
    if migration_url is None:
        raise RuntimeError(
            "MIGRATION_DATABASE_URL is required for PostgreSQL integration tests"
        )
    migration_engine = create_engine(
        migration_url,
        pool_pre_ping=True,
    )
    migration_schema_engine = None
    with migration_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        if connection.scalar(
            text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ledgerline_app')")
        ):
            connection.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO ledgerline_app'))
    migration_schema_engine = create_engine(
        migration_url,
        connect_args={"options": f"-c search_path={schema}"},
        pool_pre_ping=True,
    )
    migration_runtime = sessionmaker(bind=migration_schema_engine, autoflush=False)
    isolated_engine = create_engine(
        settings.database_url,
        connect_args={"options": f"-c search_path={schema}"},
        pool_pre_ping=True,
    )
    try:
        with migration_schema_engine.connect() as connection:
            if connection.scalar(text("SELECT current_user")) == "ledgerline_app":
                raise RuntimeError(
                    "MIGRATION_DATABASE_URL must use the privileged object-owner "
                    "role, not ledgerline_app"
                )

        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with migration_schema_engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()

        factory = sessionmaker(
            bind=isolated_engine,
            autoflush=False,
            expire_on_commit=False,
        )
        with factory() as session:
            if session.scalar(text("SELECT current_user")) != "ledgerline_app":
                raise RuntimeError(
                    "DATABASE_URL must connect as ledgerline_app for runtime-role tests"
                )
        _setup_factories[schema] = migration_runtime
        yield factory
    finally:
        _setup_factories.pop(schema, None)
        isolated_engine.dispose()
        migration_schema_engine.dispose()
        with migration_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        migration_engine.dispose()


@pytest.fixture
def transaction_client(
    transaction_factory: sessionmaker[Session],
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    def override_get_db() -> Iterator[Session]:
        with transaction_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, transaction_factory
    finally:
        app.dependency_overrides.clear()


def create_user(
    factory: sessionmaker[Session],
    role: UserRole = UserRole.ACCOUNT_HOLDER,
) -> User:
    with factory() as runtime_session:
        schema = runtime_session.scalar(text("SELECT current_schema()"))
    if schema not in _setup_factories:
        raise RuntimeError("No privileged test fixture is registered for this schema")
    with _setup_factories[schema]() as session:
        user = User(
            email=f"{uuid4().hex}@transactions.test",
            password_hash=hash_password("test-only financial transaction password"),
            role=role,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _assert_permission_denied(
    factory: sessionmaker[Session],
    statement: str,
    params: dict[str, object] | None = None,
) -> None:
    with factory() as session:
        with pytest.raises(DBAPIError) as error:
            session.execute(text(statement), params or {})
        sqlstate = getattr(error.value.orig, "sqlstate", None)
        assert sqlstate == "42501"
        session.rollback()


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


def create_account(client: TestClient, user: User) -> UUID:
    response = client.post("/api/v1/accounts", headers=auth_headers(user))
    assert response.status_code == 201
    return UUID(response.json()["id"])


def post_json(
    client: TestClient,
    path: str,
    user: User,
    key: str,
    payload: dict[str, object],
):
    return client.post(
        path,
        headers={**auth_headers(user), "Idempotency-Key": key},
        json=payload,
    )


def balance_for(factory: sessionmaker[Session], account_id: UUID) -> int:
    with factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        return account.balance_paise


def ledger_balance_for(factory: sessionmaker[Session], account_id: UUID) -> int:
    with factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        value = session.scalar(
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
            ).where(LedgerEntry.ledger_account_id == account.ledger_account_id)
        )
        return int(value or 0)


def test_deposit_withdrawal_transfer_and_ledger_invariants(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    sender = create_user(factory)
    recipient = create_user(factory)
    sender_account = create_account(client, sender)
    recipient_account = create_account(client, recipient)

    deposit_response = post_json(
        client,
        "/api/v1/transactions/deposits",
        sender,
        "deposit-1",
        {"account_id": str(sender_account), "amount_paise": 15_000},
    )
    withdrawal_response = post_json(
        client,
        "/api/v1/transactions/withdrawals",
        sender,
        "withdraw-1",
        {"account_id": str(sender_account), "amount_paise": 2_000},
    )
    transfer_response = post_json(
        client,
        "/api/v1/transactions/transfers",
        sender,
        "transfer-1",
        {
            "source_account_id": str(sender_account),
            "destination_account_id": str(recipient_account),
            "amount_paise": 3_000,
        },
    )

    assert deposit_response.status_code == 201
    assert withdrawal_response.status_code == 201
    assert transfer_response.status_code == 201
    assert balance_for(factory, sender_account) == 10_000
    assert balance_for(factory, recipient_account) == 3_000
    assert ledger_balance_for(factory, sender_account) == 10_000
    assert ledger_balance_for(factory, recipient_account) == 3_000

    with factory() as session:
        transactions = session.scalars(select(JournalTransaction)).all()
        assert {tx.transaction_type for tx in transactions} == {
            JournalTransactionType.DEPOSIT,
            JournalTransactionType.WITHDRAWAL,
            JournalTransactionType.TRANSFER,
        }
        for transaction in transactions:
            entries = session.scalars(
                select(LedgerEntry).where(
                    LedgerEntry.journal_transaction_id == transaction.id
                )
            ).all()
            assert transaction.status is JournalTransactionStatus.POSTED
            assert len(entries) == 2
            assert sum(entry.amount_paise for entry in entries if entry.entry_type is LedgerEntryType.DEBIT) == sum(
                entry.amount_paise for entry in entries if entry.entry_type is LedgerEntryType.CREDIT
            )
        clearing_accounts = session.scalars(
            select(LedgerAccount).where(
                LedgerAccount.kind.in_(
                    [LedgerAccountKind.DEPOSIT_CLEARING, LedgerAccountKind.WITHDRAWAL_CLEARING]
                )
            )
        ).all()
        assert len(clearing_accounts) == 2
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.actor_user_id == sender.id,
                AuditEvent.event_type.in_(["DEPOSIT", "WITHDRAWAL", "TRANSFER"]),
            )
        ) == 3


def test_idempotency_replays_original_result_and_rejects_changed_payload(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)
    payload = {"account_id": str(account_id), "amount_paise": 5_000}

    first = post_json(client, "/api/v1/transactions/deposits", owner, "stable-key", payload)
    replay = post_json(client, "/api/v1/transactions/deposits", owner, "stable-key", payload)
    changed = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "stable-key",
        {"account_id": str(account_id), "amount_paise": 6_000},
    )

    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]
    assert changed.status_code == 409
    assert balance_for(factory, account_id) == 5_000
    another_owner = create_user(factory)
    another_account = create_account(client, another_owner)
    same_key_other_user = post_json(
        client,
        "/api/v1/transactions/deposits",
        another_owner,
        "stable-key",
        {"account_id": str(another_account), "amount_paise": 1_000},
    )
    assert same_key_other_user.status_code == 201
    assert balance_for(factory, another_account) == 1_000
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(JournalTransaction)
            .where(JournalTransaction.initiated_by_user_id == owner.id)
        ) == 1
        assert session.scalar(
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(IdempotencyRecord.user_id == owner.id)
        ) == 1
        mismatch = session.scalar(
            select(AuditEvent).where(
                AuditEvent.actor_user_id == owner.id,
                AuditEvent.event_type == "DEPOSIT_REJECTED",
            )
        )
        assert mismatch is not None
        assert mismatch.details["reason"] == "idempotency_payload_mismatch"


def test_insufficient_funds_is_idempotently_rejected_and_audited(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)
    payload = {"account_id": str(account_id), "amount_paise": 100}

    first = post_json(client, "/api/v1/transactions/withdrawals", owner, "no-funds", payload)
    replay = post_json(client, "/api/v1/transactions/withdrawals", owner, "no-funds", payload)

    assert first.status_code == replay.status_code == 409
    assert first.json()["detail"] == "Insufficient funds"
    assert balance_for(factory, account_id) == 0
    assert ledger_balance_for(factory, account_id) == 0
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(JournalTransaction)
            .where(JournalTransaction.initiated_by_user_id == owner.id)
        ) == 0
        record = session.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.user_id == owner.id)
        )
        assert record is not None
        assert record.outcome.value == "REJECTED"
        assert record.result_code == "insufficient_funds"
        rejected = session.scalar(
            select(AuditEvent).where(
                AuditEvent.actor_user_id == owner.id,
                AuditEvent.event_type == "WITHDRAWAL_REJECTED",
            )
        )
        assert rejected is not None
        assert rejected.outcome == "REJECTED"


def test_unauthorised_access_auditor_read_only_and_owner_checks(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    other_owner = create_user(factory)
    admin = create_user(factory, UserRole.ADMIN)
    auditor = create_user(factory, UserRole.AUDITOR)
    other_account = create_account(client, other_owner)
    owner_account = create_account(client, owner)

    foreign_deposit = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "foreign-deposit",
        {"account_id": str(other_account), "amount_paise": 100},
    )
    auditor_deposit = post_json(
        client,
        "/api/v1/transactions/deposits",
        auditor,
        "auditor-deposit",
        {"account_id": str(owner_account), "amount_paise": 100},
    )
    auditor_withdrawal = post_json(
        client,
        "/api/v1/transactions/withdrawals",
        auditor,
        "auditor-withdrawal",
        {"account_id": str(owner_account), "amount_paise": 1},
    )
    auditor_transfer = post_json(
        client,
        "/api/v1/transactions/transfers",
        auditor,
        "auditor-transfer",
        {
            "source_account_id": str(owner_account),
            "destination_account_id": str(other_account),
            "amount_paise": 1,
        },
    )
    auditor_reversal = post_json(
        client,
        f"/api/v1/transactions/{uuid4()}/reverse",
        auditor,
        "auditor-reversal",
        {},
    )
    foreign_source_transfer = post_json(
        client,
        "/api/v1/transactions/transfers",
        owner,
        "foreign-source-transfer",
        {
            "source_account_id": str(other_account),
            "destination_account_id": str(owner_account),
            "amount_paise": 1,
        },
    )
    admin_deposit = post_json(
        client,
        "/api/v1/transactions/deposits",
        admin,
        "admin-deposit",
        {"account_id": str(owner_account), "amount_paise": 100},
    )
    auditor_history = client.get(
        "/api/v1/transactions",
        headers=auth_headers(auditor),
    )
    foreign_history = client.get(
        "/api/v1/transactions",
        headers=auth_headers(owner),
        params={"account_id": str(other_account)},
    )
    auditor_statement = client.get(
        f"/api/v1/accounts/{owner_account}/statement",
        headers=auth_headers(auditor),
    )
    auditor_audit_history = client.get(
        "/api/v1/audit-events",
        headers=auth_headers(auditor),
    )

    assert foreign_deposit.status_code == 404
    assert auditor_deposit.status_code == 403
    assert auditor_withdrawal.status_code == 403
    assert auditor_transfer.status_code == 403
    assert auditor_reversal.status_code == 403
    assert foreign_source_transfer.status_code == 404
    assert admin_deposit.status_code == 403
    assert auditor_history.status_code == 200
    assert foreign_history.status_code == 404
    assert auditor_statement.status_code == 200
    assert auditor_audit_history.status_code == 200
    assert balance_for(factory, owner_account) == 0
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(JournalTransaction)
            .where(
                JournalTransaction.initiated_by_user_id.in_(
                    [owner.id, auditor.id, admin.id]
                )
            )
        ) == 0
        rejected_events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.actor_user_id.in_([owner.id, auditor.id, admin.id]),
                AuditEvent.outcome == "REJECTED",
            )
        ).all()
        assert len(rejected_events) == 7


def test_reversal_posts_opposite_entries_and_adjusts_balance(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    admin = create_user(factory, UserRole.ADMIN)
    account_id = create_account(client, owner)
    deposited = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "reverse-deposit",
        {"account_id": str(account_id), "amount_paise": 4_000},
    )
    transaction_id = UUID(deposited.json()["id"])

    denied = post_json(
        client,
        f"/api/v1/transactions/{transaction_id}/reverse",
        owner,
        "holder-reversal",
        {},
    )
    reversed_response = post_json(
        client,
        f"/api/v1/transactions/{transaction_id}/reverse",
        admin,
        "admin-reversal",
        {},
    )
    second_reversal = post_json(
        client,
        f"/api/v1/transactions/{transaction_id}/reverse",
        admin,
        "admin-reversal-2",
        {},
    )

    assert denied.status_code == 403
    assert reversed_response.status_code == 201
    assert reversed_response.json()["transaction_type"] == "REVERSAL"
    assert second_reversal.status_code == 409
    assert balance_for(factory, account_id) == 0
    assert ledger_balance_for(factory, account_id) == 0
    with factory() as session:
        reversal_events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type == "REVERSAL",
                AuditEvent.actor_user_id == admin.id,
            )
        ).all()
        rejection_events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type == "REVERSAL_REJECTED",
                AuditEvent.actor_user_id.in_([owner.id, admin.id]),
            )
        ).all()
        assert len(reversal_events) == 1
        assert reversal_events[0].journal_transaction_id == UUID(reversed_response.json()["id"])
        assert len(rejection_events) == 2
        assert {event.actor_user_id for event in rejection_events} == {owner.id, admin.id}


def test_transfer_reversal_restores_both_account_balances(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    sender = create_user(factory)
    recipient = create_user(factory)
    admin = create_user(factory, UserRole.ADMIN)
    source_id = create_account(client, sender)
    destination_id = create_account(client, recipient)
    assert post_json(
        client,
        "/api/v1/transactions/deposits",
        sender,
        "transfer-reversal-funding",
        {"account_id": str(source_id), "amount_paise": 2_000},
    ).status_code == 201
    transfer_response = post_json(
        client,
        "/api/v1/transactions/transfers",
        sender,
        "transfer-to-reverse",
        {
            "source_account_id": str(source_id),
            "destination_account_id": str(destination_id),
            "amount_paise": 1_200,
        },
    )
    transfer_id = transfer_response.json()["id"]

    reversal = post_json(
        client,
        f"/api/v1/transactions/{transfer_id}/reverse",
        admin,
        "reverse-transfer",
        {},
    )

    assert reversal.status_code == 201
    assert balance_for(factory, source_id) == 2_000
    assert balance_for(factory, destination_id) == 0
    assert ledger_balance_for(factory, source_id) == 2_000
    assert ledger_balance_for(factory, destination_id) == 0


def test_frozen_account_rejects_and_audits_financial_operation(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    admin = create_user(factory, UserRole.ADMIN)
    account_id = create_account(client, owner)
    status_response = client.patch(
        f"/api/v1/accounts/{account_id}/status",
        headers=auth_headers(admin),
        json={"status": "FROZEN"},
    )
    rejected = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "frozen-deposit",
        {"account_id": str(account_id), "amount_paise": 100},
    )

    assert status_response.status_code == 200
    assert rejected.status_code == 409
    assert balance_for(factory, account_id) == 0
    closed_account_id = create_account(client, owner)
    closed_status = client.patch(
        f"/api/v1/accounts/{closed_account_id}/status",
        headers=auth_headers(admin),
        json={"status": "CLOSED"},
    )
    closed_deposit = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "closed-deposit",
        {"account_id": str(closed_account_id), "amount_paise": 100},
    )
    assert closed_status.status_code == 200
    assert closed_deposit.status_code == 409
    assert balance_for(factory, closed_account_id) == 0
    with factory() as session:
        events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.actor_user_id == owner.id,
                AuditEvent.event_type == "DEPOSIT_REJECTED",
            )
        ).all()
        assert len(events) == 2
        assert all(event.details["reason"] == "account_not_active" for event in events)


def test_posted_journal_and_entries_are_database_immutable(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)
    response = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "immutable-post",
        {"account_id": str(account_id), "amount_paise": 1_000},
    )
    transaction_id = UUID(response.json()["id"])

    _assert_permission_denied(
        factory,
        "UPDATE ledger_entries SET amount_paise = 2 WHERE journal_transaction_id = :id",
        {"id": transaction_id},
    )
    _assert_permission_denied(
        factory,
        "UPDATE journal_transactions SET amount_paise = 2 WHERE id = :id",
        {"id": transaction_id},
    )


def test_database_rejects_unbalanced_posting_and_unledgered_balance_change(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    _, factory = transaction_client
    owner = create_user(factory)
    with factory() as session:
        account = Account(
            account_number=f"LL{uuid4().int % 10**10:010d}",
            owner_user_id=owner.id,
            ledger_account_id=uuid4(),
        )
        ledger = LedgerAccount(owner_user_id=owner.id)
        session.add(ledger)
        session.flush()
        account.ledger_account_id = ledger.id
        session.add(account)
        session.commit()
        account_id = account.id
        ledger_id = ledger.id

    with factory() as session:
        journal = JournalTransaction(
            transaction_type=JournalTransactionType.DEPOSIT,
            amount_paise=100,
            source_account_id=None,
            destination_account_id=account_id,
            initiated_by_user_id=owner.id,
        )
        session.add(journal)
        session.flush()
        session.add(
            LedgerEntry(
                journal_transaction_id=journal.id,
                ledger_account_id=ledger_id,
                entry_type=LedgerEntryType.CREDIT,
                amount_paise=100,
            )
        )
        session.flush()
        session.execute(
            select(func.ledgerline_mark_journal_posted(journal.id))
        )
        with pytest.raises(DBAPIError) as error:
            session.commit()
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"
        session.rollback()

    with factory() as session:
        session.execute(
            text("UPDATE accounts SET balance_paise = 100 WHERE id = :id"),
            {"id": account_id},
        )
        with pytest.raises(DBAPIError) as error:
            session.commit()
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"
        session.rollback()
        account = session.get(Account, account_id)
        assert account is not None
        assert account.balance_paise == 0


def test_runtime_role_cannot_change_user_privileges_or_account_ownership(
    transaction_factory: sessionmaker[Session],
) -> None:
    user = create_user(transaction_factory)
    _assert_permission_denied(
        transaction_factory,
        "INSERT INTO users (id, email, password_hash, role) "
        "VALUES (:id, :email, :password_hash, 'ADMIN')",
        {
            "id": uuid4(),
            "email": f"{uuid4().hex}@privilege.test",
            "password_hash": "not-a-real-password-hash",
        },
    )
    _assert_permission_denied(
        transaction_factory,
        "UPDATE users SET role = 'ADMIN' WHERE id = :user_id",
        {"user_id": user.id},
    )
    _assert_permission_denied(
        transaction_factory,
        "UPDATE accounts SET owner_user_id = :other WHERE owner_user_id = :user_id",
        {"other": uuid4(), "user_id": user.id},
    )
    _assert_permission_denied(
        transaction_factory,
        "INSERT INTO accounts "
        "(id, account_number, owner_user_id, ledger_account_id, balance_paise) "
        "VALUES (:id, :account_number, :owner_user_id, :ledger_account_id, 0)",
        {
            "id": uuid4(),
            "account_number": f"LL{uuid4().int % 10_000_000_000:010d}",
            "owner_user_id": user.id,
            "ledger_account_id": uuid4(),
        },
    )
    _assert_permission_denied(
        transaction_factory,
        "INSERT INTO ledger_accounts (id, kind, system_code) "
        "VALUES (:id, 'DEPOSIT_CLEARING', 'forbidden-clearing-account')",
        {"id": uuid4()},
    )


def test_runtime_role_has_only_justified_table_permissions(
    transaction_factory: sessionmaker[Session],
) -> None:
    with transaction_factory() as session:
        assert session.scalar(text("SELECT current_user")) == "ledgerline_app"
        privileges = session.execute(
            text(
                """
                SELECT table_name,
                       has_table_privilege(
                           current_user,
                           format('%I.%I', current_schema(), table_name)::regclass,
                           'SELECT'
                       ) AS can_select,
                       has_table_privilege(
                           current_user,
                           format('%I.%I', current_schema(), table_name)::regclass,
                           'INSERT'
                       ) AS table_insert,
                       has_table_privilege(
                           current_user,
                           format('%I.%I', current_schema(), table_name)::regclass,
                           'UPDATE'
                       ) AS table_update,
                       has_table_privilege(
                           current_user,
                           format('%I.%I', current_schema(), table_name)::regclass,
                           'DELETE'
                       ) AS can_delete
                FROM unnest(ARRAY[
                    'users', 'accounts', 'ledger_accounts', 'journal_transactions',
                    'ledger_entries', 'idempotency_records', 'audit_events',
                    'alembic_version'
                ]) AS permissions(table_name)
                """
            )
        ).mappings().all()
        by_table = {row["table_name"]: row for row in privileges}
        for table_name in (
            "users",
            "accounts",
            "ledger_accounts",
            "journal_transactions",
            "ledger_entries",
            "idempotency_records",
            "audit_events",
        ):
            assert by_table[table_name]["can_select"]
            assert not by_table[table_name]["table_insert"]
            assert not by_table[table_name]["table_update"]
            assert not by_table[table_name]["can_delete"]
        assert not any(
            by_table["alembic_version"][privilege]
            for privilege in ("can_select", "table_insert", "table_update", "can_delete")
        )
        assert session.scalar(
            text(
                """
                SELECT has_column_privilege(
                           current_user, 'users', 'email', 'INSERT'
                       )
                   AND has_column_privilege(
                           current_user, 'users', 'password_hash', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'users', 'role', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'users', 'status', 'INSERT'
                       )
                   AND has_column_privilege(
                           current_user, 'accounts', 'owner_user_id', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'accounts', 'balance_paise', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'accounts', 'status', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'accounts', 'owner_user_id', 'UPDATE'
                       )
                   AND has_column_privilege(
                           current_user, 'accounts', 'balance_paise', 'UPDATE'
                       )
                   AND has_column_privilege(
                           current_user, 'accounts', 'status', 'UPDATE'
                       )
                   AND has_column_privilege(
                           current_user, 'ledger_accounts', 'owner_user_id', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'ledger_accounts', 'kind', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'ledger_accounts', 'system_code', 'INSERT'
                       )
                   AND has_column_privilege(
                           current_user, 'journal_transactions', 'initiated_by_user_id', 'INSERT'
                       )
                   AND NOT has_column_privilege(
                           current_user, 'journal_transactions', 'status', 'INSERT'
                       )
                """
            )
        )
        role_state = session.execute(
            text(
                """
                SELECT rolsuper AS superuser, rolcreatedb, rolcreaterole,
                       has_database_privilege(current_user, current_database(), 'CREATE')
                           AS can_create_database_objects,
                       has_schema_privilege(current_user, current_schema(), 'CREATE')
                           AS can_create_in_schema,
                       EXISTS (
                           SELECT 1 FROM pg_auth_members
                           WHERE member = current_user::regrole
                       ) AS has_role_memberships
                FROM pg_roles WHERE rolname = current_user
                """
            )
        ).mappings().one()
        assert not role_state["superuser"]
        assert not role_state["rolcreatedb"]
        assert not role_state["rolcreaterole"]
        assert not role_state["can_create_database_objects"]
        assert not role_state["can_create_in_schema"]
        assert not role_state["has_role_memberships"]
        assert session.scalar(
            text(
                """
                SELECT NOT EXISTS (
                    SELECT 1
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = current_schema()
                      AND c.relkind = 'S'
                      AND has_sequence_privilege(current_user, c.oid, 'USAGE')
                )
                """
            )
        )


def test_runtime_cannot_mutate_protected_records_or_ddl(
    transaction_factory: sessionmaker[Session],
) -> None:
    protected_statements = (
        "UPDATE alembic_version SET version_num = 'forbidden'",
        "UPDATE audit_events SET outcome = outcome",
        "DELETE FROM audit_events",
        "UPDATE idempotency_records SET result_code = result_code",
        "DELETE FROM idempotency_records",
        "UPDATE journal_transactions SET amount_paise = amount_paise",
        "DELETE FROM journal_transactions",
        "UPDATE ledger_entries SET amount_paise = amount_paise",
        "DELETE FROM ledger_entries",
        "UPDATE ledger_accounts SET owner_user_id = owner_user_id",
        "DELETE FROM ledger_accounts",
    )
    for statement in protected_statements:
        _assert_permission_denied(transaction_factory, statement)

    _assert_permission_denied(
        transaction_factory,
        f"CREATE SCHEMA ledgerline_forbidden_{uuid4().hex}",
    )
    _assert_permission_denied(
        transaction_factory,
        f"CREATE ROLE ledgerline_forbidden_{uuid4().hex}",
    )


def test_future_tables_do_not_receive_runtime_grants(
    transaction_factory: sessionmaker[Session],
) -> None:
    with transaction_factory() as runtime_session:
        schema = runtime_session.scalar(text("SELECT current_schema()"))
    assert schema in _setup_factories
    with _setup_factories[schema]() as setup_session:
        setup_session.execute(
            text(f'CREATE TABLE "{schema}".least_privilege_probe (id integer)')
        )
        setup_session.execute(
            text(f'CREATE SEQUENCE "{schema}".least_privilege_probe_sequence')
        )
        setup_session.commit()

    with transaction_factory() as session:
        assert not session.scalar(
            text(
                """
                SELECT has_table_privilege(
                    current_user,
                    format('%I.%I', CAST(:schema_name AS text), 'least_privilege_probe')::regclass,
                    'SELECT'
                )
                """
            ),
            {"schema_name": schema},
        )
        assert session.scalar(
            text(
                """
                SELECT NOT has_sequence_privilege(
                           current_user,
                           format(
                               '%I.%I',
                               CAST(:schema_name AS text),
                               'least_privilege_probe_sequence'
                           )::regclass,
                           'USAGE'
                       )
                   AND NOT has_sequence_privilege(
                           current_user,
                           format(
                               '%I.%I',
                               CAST(:schema_name AS text),
                               'least_privilege_probe_sequence'
                           )::regclass,
                           'SELECT'
                       )
                   AND NOT has_sequence_privilege(
                           current_user,
                           format(
                               '%I.%I',
                               CAST(:schema_name AS text),
                               'least_privilege_probe_sequence'
                           )::regclass,
                           'UPDATE'
                       )
                """
            ),
            {"schema_name": schema},
        )
        assert not session.scalar(
            text(
                """
                SELECT has_table_privilege(
                    current_user,
                    format('%I.%I', CAST(:schema_name AS text), 'least_privilege_probe')::regclass,
                    'INSERT'
                )
                """
            ),
            {"schema_name": schema},
        )


def test_runtime_role_can_choose_account_owner_on_insert(
    transaction_factory: sessionmaker[Session],
) -> None:
    actor = create_user(transaction_factory)
    owner = create_user(transaction_factory)
    assert actor.id != owner.id
    ledger_account_id = uuid4()
    account_id = uuid4()
    account_number = f"LL{uuid4().int % 10_000_000_000:010d}"
    with transaction_factory() as session:
        session.execute(
            text(
                "INSERT INTO ledger_accounts (id, owner_user_id) "
                "VALUES (:id, :owner_user_id)"
            ),
            {"id": ledger_account_id, "owner_user_id": owner.id},
        )
        session.execute(
            text(
                "INSERT INTO accounts (id, account_number, owner_user_id, ledger_account_id) "
                "VALUES (:id, :account_number, :owner_user_id, :ledger_account_id)"
            ),
            {
                "id": account_id,
                "account_number": account_number,
                "owner_user_id": owner.id,
                "ledger_account_id": ledger_account_id,
            },
        )
        session.commit()

    with transaction_factory() as session:
        assert session.scalar(
            select(Account.owner_user_id).where(Account.id == account_id)
        ) == owner.id


def test_direct_balance_change_is_trigger_rejected_not_permission_denied(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)
    with factory() as session:
        session.execute(
            text("UPDATE accounts SET balance_paise = 100 WHERE id = :account_id"),
            {"account_id": account_id},
        )
        with pytest.raises(DBAPIError) as error:
            session.commit()
        assert getattr(error.value.orig, "sqlstate", None) == "P0001"
        session.rollback()

    assert balance_for(factory, account_id) == 0


def test_concurrent_withdrawals_cannot_overspend(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)
    funding = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "concurrent-funding",
        {"account_id": str(account_id), "amount_paise": 1_000},
    )
    assert funding.status_code == 201

    def withdraw_with_key(key: str):
        return post_json(
            client,
            "/api/v1/transactions/withdrawals",
            owner,
            key,
            {"account_id": str(account_id), "amount_paise": 700},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(withdraw_with_key, ("concurrent-a", "concurrent-b")))

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert balance_for(factory, account_id) == 300
    assert ledger_balance_for(factory, account_id) == 300


def test_concurrent_transfers_cannot_overspend(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    sender = create_user(factory)
    first_recipient = create_user(factory)
    second_recipient = create_user(factory)
    source_id = create_account(client, sender)
    first_recipient_id = create_account(client, first_recipient)
    second_recipient_id = create_account(client, second_recipient)
    assert post_json(
        client,
        "/api/v1/transactions/deposits",
        sender,
        "transfer-funding",
        {"account_id": str(source_id), "amount_paise": 1_000},
    ).status_code == 201

    def transfer_to(destination_id: UUID, key: str):
        return post_json(
            client,
            "/api/v1/transactions/transfers",
            sender,
            key,
            {
                "source_account_id": str(source_id),
                "destination_account_id": str(destination_id),
                "amount_paise": 700,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda args: transfer_to(*args),
                (
                    (first_recipient_id, "concurrent-transfer-a"),
                    (second_recipient_id, "concurrent-transfer-b"),
                ),
            )
        )

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert balance_for(factory, source_id) == 300
    assert ledger_balance_for(factory, source_id) == 300
    assert (
        balance_for(factory, first_recipient_id)
        + balance_for(factory, second_recipient_id)
    ) == 700


def test_concurrent_reversals_post_only_one_compensation(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    admin = create_user(factory, UserRole.ADMIN)
    account_id = create_account(client, owner)
    deposit = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "concurrent-reversal-funding",
        {"account_id": str(account_id), "amount_paise": 1_500},
    )
    transaction_id = deposit.json()["id"]

    def reverse(key: str):
        return post_json(
            client,
            f"/api/v1/transactions/{transaction_id}/reverse",
            admin,
            key,
            {},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(reverse, ("concurrent-reversal-a", "concurrent-reversal-b"))
        )

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert balance_for(factory, account_id) == 0
    assert ledger_balance_for(factory, account_id) == 0
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(JournalTransaction)
            .where(
                JournalTransaction.related_transaction_id == UUID(transaction_id)
            )
        ) == 1
        assert session.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.journal_transaction_id.in_(
                select(JournalTransaction.id).where(
                    JournalTransaction.related_transaction_id == UUID(transaction_id)
                )
            ))
        ) == 2


def test_concurrent_duplicate_idempotency_posts_once(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)

    def deposit_once():
        return post_json(
            client,
            "/api/v1/transactions/deposits",
            owner,
            "simultaneous-same-key",
            {"account_id": str(account_id), "amount_paise": 2_500},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: deposit_once(), range(2)))

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert balance_for(factory, account_id) == 2_500
    assert ledger_balance_for(factory, account_id) == 2_500
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(JournalTransaction)
            .where(JournalTransaction.initiated_by_user_id == owner.id)
        ) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.actor_user_id == owner.id,
                AuditEvent.outcome == "SUCCEEDED",
                AuditEvent.event_type == "DEPOSIT",
            )
        ) == 1


def test_concurrent_duplicate_rejection_is_audited_once(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)

    def rejected_with_same_key():
        return post_json(
            client,
            "/api/v1/transactions/withdrawals",
            owner,
            "same-rejected-key",
            {"account_id": str(account_id), "amount_paise": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: rejected_with_same_key(), range(2)))

    assert [response.status_code for response in responses] == [409, 409]
    with factory() as session:
        assert session.scalar(
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(IdempotencyRecord.user_id == owner.id)
        ) == 1
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.actor_user_id == owner.id,
                AuditEvent.outcome == "REJECTED",
            )
        ) == 1


def test_database_commit_failure_rolls_back_balance_ledger_idempotency_and_audit(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)

    def create_unbalanced_journal(
        db: Session,
        actor: User,
        transaction_type: JournalTransactionType,
        amount_paise: int,
        source_account_id: UUID | None,
        destination_account_id: UUID | None,
        entries: list[tuple[UUID, LedgerEntryType]],
        related_transaction_id: UUID | None = None,
    ) -> JournalTransaction:
        journal = JournalTransaction(
            transaction_type=transaction_type,
            status=JournalTransactionStatus.POSTING,
            amount_paise=amount_paise,
            currency="INR",
            source_account_id=source_account_id,
            destination_account_id=destination_account_id,
            related_transaction_id=related_transaction_id,
            initiated_by_user_id=actor.id,
        )
        db.add(journal)
        db.flush()
        db.add(
            LedgerEntry(
                journal_transaction_id=journal.id,
                ledger_account_id=entries[0][0],
                entry_type=entries[0][1],
                amount_paise=amount_paise,
                currency="INR",
            )
        )
        db.flush()
        db.execute(
            select(func.ledgerline_mark_journal_posted(journal.id))
        )
        return journal

    monkeypatch.setattr(
        transaction_service,
        "_create_posted_journal",
        create_unbalanced_journal,
    )
    with factory() as session:
        with pytest.raises(DBAPIError):
            transaction_service.deposit(
                session,
                owner,
                account_id,
                900,
                "deferred-trigger-rollback",
            )

    with factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        assert account.balance_paise == 0
        assert session.scalar(
            select(func.count())
            .select_from(JournalTransaction)
            .where(JournalTransaction.initiated_by_user_id == owner.id)
        ) == 0
        assert session.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(
                LedgerEntry.journal_transaction_id.in_(
                    select(JournalTransaction.id).where(
                        JournalTransaction.initiated_by_user_id == owner.id
                    )
                )
            )
        ) == 0
        assert session.scalar(
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(IdempotencyRecord.user_id == owner.id)
        ) == 0
        failure_audit = session.scalar(
            select(AuditEvent).where(
                AuditEvent.actor_user_id == owner.id,
                AuditEvent.event_type == "DEPOSIT_REJECTED",
            )
        )
        assert failure_audit is not None
        assert failure_audit.outcome == "REJECTED"
        assert failure_audit.details["reason"] == "internal_error"
        assert session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.actor_user_id == owner.id)
        ) == 2


def test_transaction_history_and_statement_are_owner_scoped(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    stranger = create_user(factory)
    account_id = create_account(client, owner)

    posted = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "statement-deposit",
        {"account_id": str(account_id), "amount_paise": 700},
    )
    history = client.get("/api/v1/transactions", headers=auth_headers(owner))
    statement = client.get(
        f"/api/v1/accounts/{account_id}/statement",
        headers=auth_headers(owner),
    )
    foreign_statement = client.get(
        f"/api/v1/accounts/{account_id}/statement",
        headers=auth_headers(stranger),
    )

    assert posted.status_code == 201
    assert len(history.json()) == 1
    assert statement.status_code == 200
    assert statement.json()["opening_balance_paise"] == 0
    assert statement.json()["closing_balance_paise"] == 700
    assert statement.json()["entries"][0]["balance_after_paise"] == 700
    assert foreign_statement.status_code == 404


def test_requests_validate_positive_paise_and_required_idempotency_key(
    transaction_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = transaction_client
    owner = create_user(factory)
    account_id = create_account(client, owner)
    zero = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "zero-amount",
        {"account_id": str(account_id), "amount_paise": 0},
    )
    too_large = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "large-amount",
        {"account_id": str(account_id), "amount_paise": MAX_AMOUNT_PAISE + 1},
    )
    fractional = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "fractional-amount",
        {"account_id": str(account_id), "amount_paise": 1.5},
    )
    forged_fields = post_json(
        client,
        "/api/v1/transactions/deposits",
        owner,
        "forged-financial-fields",
        {
            "account_id": str(account_id),
            "amount_paise": 1,
            "owner_user_id": str(uuid4()),
            "balance_paise": 9_999_999,
        },
    )
    missing_key = client.post(
        "/api/v1/transactions/deposits",
        headers=auth_headers(owner),
        json={"account_id": str(account_id), "amount_paise": 1},
    )

    assert zero.status_code == 422
    assert too_large.status_code == 422
    assert fractional.status_code == 422
    assert forged_fields.status_code == 422
    assert missing_key.status_code == 422
    assert balance_for(factory, account_id) == 0
