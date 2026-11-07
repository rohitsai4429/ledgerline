from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_migration_database_url, get_settings
from app.core.security import create_access_token, hash_password
from app.database.session import get_db
from app.main import app
from app.models.account import Account, AccountStatus, LedgerAccount
from app.models.transaction import AuditEvent
from app.models.user import User, UserRole, UserStatus

_setup_factories: dict[str, sessionmaker[Session]] = {}


@pytest.fixture(scope="module")
def account_database() -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    schema = f"ledgerline_accounts_test_{uuid4().hex}"
    migration_url = get_migration_database_url()
    if migration_url is None:
        raise RuntimeError(
            "MIGRATION_DATABASE_URL is required for PostgreSQL integration tests"
        )
    migration_engine = create_engine(migration_url, pool_pre_ping=True)
    with migration_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO ledgerline_app'))

    migration_schema_engine = create_engine(
        migration_url,
        connect_args={"options": f"-c search_path={schema}"},
        pool_pre_ping=True,
    )
    runtime_engine = create_engine(
        get_settings().database_url,
        connect_args={"options": f"-c search_path={schema}"},
        pool_pre_ping=True,
    )
    try:
        with migration_schema_engine.connect() as connection:
            if connection.scalar(text("SELECT current_user")) != "ledgerline_user":
                raise RuntimeError(
                    "MIGRATION_DATABASE_URL must connect as ledgerline_user "
                    "to apply its default privileges"
                )

        with migration_schema_engine.connect() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()

        with runtime_engine.connect() as connection:
            if connection.scalar(text("SELECT current_user")) != "ledgerline_app":
                raise RuntimeError(
                    "DATABASE_URL must connect as ledgerline_app for runtime-role tests"
                )
        setup_factory = sessionmaker(
            bind=migration_schema_engine,
            autoflush=False,
            expire_on_commit=False,
        )
        _setup_factories[schema] = setup_factory
        yield runtime_engine, setup_factory
    finally:
        _setup_factories.pop(schema, None)
        runtime_engine.dispose()
        migration_schema_engine.dispose()
        with migration_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        migration_engine.dispose()


@pytest.fixture
def postgres_client(
    account_database: tuple[Engine, sessionmaker[Session]],
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    runtime_engine, _ = account_database
    connection = runtime_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        transaction.rollback()
        connection.close()


def create_user(factory: sessionmaker[Session], email: str, role: UserRole) -> User:
    with factory() as runtime_session:
        schema = runtime_session.scalar(text("SELECT current_schema()"))
    if schema not in _setup_factories:
        raise RuntimeError("No privileged test fixture is registered for this schema")
    with _setup_factories[schema]() as session:
        user = User(
            email=email,
            password_hash=hash_password("postgres integration test password"),
            role=role,
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def headers_for(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


def create_account(client: TestClient, user: User) -> dict[str, object]:
    response = client.post("/api/v1/accounts", headers=headers_for(user))
    assert response.status_code == 201
    return response.json()


def test_account_creation_generates_number_and_linked_zero_balance(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-create@example.com", UserRole.ACCOUNT_HOLDER)

    response = client.post("/api/v1/accounts", headers=headers_for(owner))

    assert response.status_code == 201
    data = response.json()
    assert len(data["account_number"]) == 12
    assert data["account_number"].startswith("LL")
    assert data["balance_paise"] == 0
    assert data["status"] == AccountStatus.ACTIVE.value
    assert UUID(data["owner_user_id"]) == owner.id

    with factory() as session:
        account_event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "ACCOUNT_CREATED",
                AuditEvent.actor_user_id == owner.id,
            )
        )
        account = session.get(Account, UUID(data["id"]))
        assert account is not None
        assert account_event is not None
        assert account_event.details == {"account_id": data["id"]}
        ledger_account = session.get(LedgerAccount, account.ledger_account_id)
        assert ledger_account is not None
        assert ledger_account.owner_user_id == owner.id
        assert account.owner_user_id == ledger_account.owner_user_id
        second_account = create_account(client, owner)
        assert second_account["account_number"] != data["account_number"]


def test_registration_login_and_current_user_work_with_runtime_grants(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    email = f"{uuid4().hex}@example.com"
    password = "postgres-only integration password"

    registration = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert registration.status_code == 201
    assert registration.json()["role"] == UserRole.ACCOUNT_HOLDER.value
    assert registration.json()["status"] == UserStatus.ACTIVE.value

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert profile.status_code == 200
    assert profile.json()["id"] == registration.json()["id"]
    assert "password_hash" not in profile.json()

    with factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.role is UserRole.ACCOUNT_HOLDER
        assert user.status is UserStatus.ACTIVE
        assert session.scalar(
            select(AuditEvent).where(
                AuditEvent.actor_user_id == user.id,
                AuditEvent.event_type == "LOGIN_SUCCEEDED",
            )
        ) is not None


def test_only_account_holders_can_create_accounts(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    admin = create_user(factory, "account-admin@example.com", UserRole.ADMIN)
    auditor = create_user(factory, "account-auditor@example.com", UserRole.AUDITOR)

    assert client.post("/api/v1/accounts", headers=headers_for(admin)).status_code == 403
    assert client.post("/api/v1/accounts", headers=headers_for(auditor)).status_code == 403
    with factory() as session:
        events = session.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type == "AUTHORIZATION_REJECTED",
                AuditEvent.actor_user_id.in_([admin.id, auditor.id]),
            )
        ).all()
        assert len(events) == 2
        assert {event.details["path"] for event in events} == {"/api/v1/accounts"}


def test_account_holder_can_only_list_and_read_owned_accounts(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-owner@example.com", UserRole.ACCOUNT_HOLDER)
    other_owner = create_user(factory, "account-other@example.com", UserRole.ACCOUNT_HOLDER)
    own_account = create_account(client, owner)
    other_account = create_account(client, other_owner)
    headers = headers_for(owner)

    listing = client.get("/api/v1/accounts", headers=headers)
    own_detail = client.get(f"/api/v1/accounts/{own_account['id']}", headers=headers)
    other_detail = client.get(f"/api/v1/accounts/{other_account['id']}", headers=headers)

    assert listing.status_code == 200
    assert [item["id"] for item in listing.json()] == [own_account["id"]]
    assert own_detail.status_code == 200
    assert other_detail.status_code == 404


def test_admin_and_auditor_can_read_all_accounts(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-read-owner@example.com", UserRole.ACCOUNT_HOLDER)
    admin = create_user(factory, "account-read-admin@example.com", UserRole.ADMIN)
    auditor = create_user(factory, "account-read-auditor@example.com", UserRole.AUDITOR)
    account = create_account(client, owner)

    for reader in (admin, auditor):
        response = client.get("/api/v1/accounts", headers=headers_for(reader))
        assert response.status_code == 200
        assert account["id"] in [item["id"] for item in response.json()]
        detail = client.get(
            f"/api/v1/accounts/{account['id']}",
            headers=headers_for(reader),
        )
        assert detail.status_code == 200


def test_only_admin_can_manage_status_and_auditors_are_read_only(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-status-owner@example.com", UserRole.ACCOUNT_HOLDER)
    admin = create_user(factory, "account-status-admin@example.com", UserRole.ADMIN)
    auditor = create_user(factory, "account-status-auditor@example.com", UserRole.AUDITOR)
    account = create_account(client, owner)
    endpoint = f"/api/v1/accounts/{account['id']}/status"

    for reader in (owner, auditor):
        response = client.patch(
            endpoint,
            headers=headers_for(reader),
            json={"status": AccountStatus.FROZEN.value},
        )
        assert response.status_code == 403

    forged_role_token = create_access_token(owner.id, UserRole.ADMIN)
    forged_role_response = client.patch(
        endpoint,
        headers={"Authorization": f"Bearer {forged_role_token}"},
        json={"status": AccountStatus.CLOSED.value},
    )
    assert forged_role_response.status_code == 403

    response = client.patch(
        endpoint,
        headers=headers_for(admin),
        json={"status": AccountStatus.FROZEN.value},
    )
    assert response.status_code == 200
    assert response.json()["status"] == AccountStatus.FROZEN.value

    with factory() as session:
        event = session.query(AuditEvent).filter_by(
            event_type="ACCOUNT_STATUS_CHANGED",
        ).one()
        assert event.actor_user_id == admin.id
        assert event.journal_transaction_id is None
        assert event.details == {
            "account_id": account["id"],
            "previous_status": AccountStatus.ACTIVE.value,
            "new_status": AccountStatus.FROZEN.value,
        }


def test_account_api_rejects_balance_mutation(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-balance-owner@example.com", UserRole.ACCOUNT_HOLDER)

    for fields in (
        {"owner_user_id": str(uuid4())},
        {"status": AccountStatus.FROZEN.value},
        {"ledger_account_id": str(uuid4())},
        {"balance_paise": 999_999},
    ):
        create_response = client.post(
            "/api/v1/accounts",
            headers=headers_for(owner),
            json=fields,
        )
        assert create_response.status_code == 422

    created = create_account(client, owner)
    admin = create_user(factory, "account-balance-admin@example.com", UserRole.ADMIN)
    update_response = client.patch(
        f"/api/v1/accounts/{created['id']}/status",
        headers=headers_for(admin),
        json={"status": AccountStatus.ACTIVE.value, "balance_paise": 999_999},
    )
    assert update_response.status_code == 422

    with factory() as session:
        account = session.get(Account, UUID(created["id"]))
        assert account is not None
        assert account.balance_paise == 0


def test_postgres_rejects_negative_balance(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-negative-balance@example.com", UserRole.ACCOUNT_HOLDER)
    account = create_account(client, owner)

    with factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(
                text("UPDATE accounts SET balance_paise = -1 WHERE id = :account_id"),
                {"account_id": UUID(account["id"])},
            )

    with factory() as session:
        stored_account = session.get(Account, UUID(account["id"]))
        assert stored_account is not None
        assert stored_account.balance_paise == 0


def test_account_status_cannot_be_reactivated_after_closure(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-close-owner@example.com", UserRole.ACCOUNT_HOLDER)
    admin = create_user(factory, "account-close-admin@example.com", UserRole.ADMIN)
    account = create_account(client, owner)
    endpoint = f"/api/v1/accounts/{account['id']}/status"

    closed = client.patch(
        endpoint,
        headers=headers_for(admin),
        json={"status": AccountStatus.CLOSED.value},
    )
    reopened = client.patch(
        endpoint,
        headers=headers_for(admin),
        json={"status": AccountStatus.ACTIVE.value},
    )

    assert closed.status_code == 200
    assert reopened.status_code == 409
    with factory() as session:
        rejected = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "ACCOUNT_STATUS_CHANGE_REJECTED",
            )
        )
        assert rejected is not None
        assert rejected.actor_user_id == admin.id
        assert rejected.details == {
            "account_id": account["id"],
            "reason": "closed_account_cannot_be_reactivated",
        }


def test_account_requires_authentication(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client = postgres_client[0]

    assert client.post("/api/v1/accounts").status_code == 401
    assert client.get("/api/v1/accounts").status_code == 401
    with postgres_client[1]() as session:
        events = [
            event
            for event in session.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type == "AUTHENTICATION_REJECTED",
            )
            ).all()
            if event.details["path"] == "/api/v1/accounts"
        ]
        assert len(events) == 2
        assert all(event.actor_user_id is None for event in events)
