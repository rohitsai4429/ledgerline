from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import create_access_token, hash_password
from app.database.session import engine, get_db
from app.main import app
from app.models.account import Account, AccountStatus, LedgerAccount
from app.models.user import User, UserRole, UserStatus


@pytest.fixture
def postgres_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    connection = engine.connect()
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
    with factory() as session:
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
        account = session.get(Account, UUID(data["id"]))
        assert account is not None
        ledger_account = session.get(LedgerAccount, account.ledger_account_id)
        assert ledger_account is not None
        assert ledger_account.owner_user_id == owner.id
        assert account.owner_user_id == ledger_account.owner_user_id
        second_account = create_account(client, owner)
        assert second_account["account_number"] != data["account_number"]


def test_only_account_holders_can_create_accounts(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    admin = create_user(factory, "account-admin@example.com", UserRole.ADMIN)
    auditor = create_user(factory, "account-auditor@example.com", UserRole.AUDITOR)

    assert client.post("/api/v1/accounts", headers=headers_for(admin)).status_code == 403
    assert client.post("/api/v1/accounts", headers=headers_for(auditor)).status_code == 403


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

    response = client.patch(
        endpoint,
        headers=headers_for(admin),
        json={"status": AccountStatus.FROZEN.value},
    )
    assert response.status_code == 200
    assert response.json()["status"] == AccountStatus.FROZEN.value


def test_account_api_rejects_balance_mutation(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgres_client
    owner = create_user(factory, "account-balance-owner@example.com", UserRole.ACCOUNT_HOLDER)

    create_response = client.post(
        "/api/v1/accounts",
        headers=headers_for(owner),
        json={"balance_paise": 999_999},
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


def test_account_requires_authentication(
    postgres_client: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client = postgres_client[0]

    assert client.post("/api/v1/accounts").status_code == 401
    assert client.get("/api/v1/accounts").status_code == 401
