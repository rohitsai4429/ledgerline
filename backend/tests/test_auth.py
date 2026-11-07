from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import require_roles
from app.core.config import get_settings
from app.core.security import create_access_token
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.transaction import AuditEvent
from app.models.user import User, UserRole, UserStatus

TEST_EMAIL = "holder@example.com"
TEST_PASSWORD = "correct horse battery staple 2026"


@pytest.fixture
def test_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(test_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_user(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()


def test_registration_normalizes_email_and_hashes_password(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  HOLDER@Example.COM  ", "password": TEST_PASSWORD},
    )

    assert response.status_code == 201
    assert response.json()["email"] == TEST_EMAIL
    assert response.json()["role"] == UserRole.ACCOUNT_HOLDER.value
    assert response.json()["status"] == UserStatus.ACTIVE.value
    assert "password_hash" not in response.json()

    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == TEST_EMAIL))
        registered_event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "USER_REGISTERED")
        )

    assert user is not None
    assert registered_event is not None
    assert registered_event.actor_user_id == user.id
    assert registered_event.details == {"role": UserRole.ACCOUNT_HOLDER.value}
    assert user.password_hash != TEST_PASSWORD
    assert PasswordHasher().verify(user.password_hash, TEST_PASSWORD)


def test_registration_rejects_duplicate_normalized_email(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    register_user(client)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": " HOLDER@EXAMPLE.COM ", "password": TEST_PASSWORD},
    )

    assert response.status_code == 409
    with test_session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "REGISTRATION_REJECTED")
        )
        assert event is not None
        assert event.actor_user_id is None
        assert event.details == {"reason": "duplicate_email"}


@pytest.mark.parametrize(
    "privileged_fields",
    [
        {"role": UserRole.ADMIN.value},
        {"role": UserRole.AUDITOR.value},
        {"status": UserStatus.DISABLED.value},
        {"id": "00000000-0000-0000-0000-000000000001"},
    ],
)
def test_registration_rejects_privileged_fields(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    privileged_fields: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, **privileged_fields},
    )

    assert response.status_code == 422
    with test_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


def test_login_issues_valid_expiring_jwt(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    registered = register_user(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "HOLDER@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    token_data = response.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == get_settings().jwt_access_token_minutes * 60
    claims = jwt.decode(
        token_data["access_token"],
        get_settings().jwt_secret_key.get_secret_value(),
        algorithms=[get_settings().jwt_algorithm],
    )
    assert claims["sub"] == registered["id"]
    assert claims["role"] == UserRole.ACCOUNT_HOLDER.value
    assert "exp" in claims
    with test_session_factory() as session:
        login_event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "LOGIN_SUCCEEDED")
        )
        assert login_event is not None
        assert login_event.actor_user_id == UUID(registered["id"])
        assert login_event.details == {}


def test_login_rejects_invalid_password(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    register_user(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": "not the password"},
    )

    assert response.status_code == 401
    with test_session_factory() as session:
        login_event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "LOGIN_REJECTED")
        )
        assert login_event is not None
        assert login_event.actor_user_id is None
        assert login_event.details == {"reason": "invalid_credentials"}


def test_login_rejects_unknown_user_without_disclosing_account_existence(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": TEST_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    with test_session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "LOGIN_REJECTED")
        )
        assert event is not None
        assert event.details == {"reason": "invalid_credentials"}


def test_login_rejects_disabled_user(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    register_user(client)
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == TEST_EMAIL))
        assert user is not None
        user.status = UserStatus.DISABLED
        session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )

    assert response.status_code == 403
    with test_session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "LOGIN_REJECTED")
        )
        assert event is not None
        assert event.actor_user_id is None
        assert event.details == {"reason": "user_disabled"}


def test_expired_jwt_is_rejected(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    register_user(client)
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == TEST_EMAIL))
        assert user is not None
        token = create_access_token(user.id, user.role, expires_delta=timedelta(seconds=-1))

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    with test_session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "AUTHENTICATION_REJECTED",
            )
        )
        assert event is not None
        assert event.actor_user_id is None
        assert event.details == {
            "method": "GET",
            "path": "/api/v1/auth/me",
            "reason": "invalid_token",
        }


@pytest.mark.parametrize("missing_claim", ["exp", "iat"])
def test_jwt_missing_required_time_claim_is_rejected(
    client: TestClient,
    missing_claim: str,
) -> None:
    registered = register_user(client)
    payload = {
        "sub": registered["id"],
        "role": UserRole.ACCOUNT_HOLDER.value,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    payload.pop(missing_claim)
    token = jwt.encode(
        payload,
        get_settings().jwt_secret_key.get_secret_value(),
        algorithm=get_settings().jwt_algorithm,
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired authentication credentials"
    }


@pytest.mark.parametrize("attack", ["malformed", "tampered", "wrong_algorithm", "missing_sub"])
def test_invalid_jwt_variants_are_rejected(
    client: TestClient,
    attack: str,
) -> None:
    registered = register_user(client)
    token = create_access_token(UUID(registered["id"]), UserRole.ACCOUNT_HOLDER)
    if attack == "malformed":
        token = "not-a-jwt"
    elif attack == "tampered":
        token = f"{token.rsplit('.', 1)[0]}.{'a' * 40}"
    elif attack == "wrong_algorithm":
        token = jwt.encode(
            {
                "sub": registered["id"],
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            get_settings().jwt_secret_key.get_secret_value(),
            algorithm="HS512",
        )
    elif attack == "missing_sub":
        token = jwt.encode(
            {
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            get_settings().jwt_secret_key.get_secret_value(),
            algorithm=get_settings().jwt_algorithm,
        )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or expired authentication credentials"
    }


def test_disabled_user_existing_token_is_rejected(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    registered = register_user(client)
    user_id = UUID(registered["id"])
    with test_session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None
        token = create_access_token(user.id, user.role)
        user.status = UserStatus.DISABLED
        session.commit()

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_current_user_endpoint_returns_safe_profile(client: TestClient) -> None:
    registered = register_user(client)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    token = login_response.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == registered["id"]
    assert response.json()["email"] == TEST_EMAIL
    assert response.json()["role"] == UserRole.ACCOUNT_HOLDER.value
    assert "password_hash" not in response.json()


def test_role_authorization_denies_insufficient_role(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    registered = register_user(client)
    user = User(
        id=UUID(registered["id"]),
        email=TEST_EMAIL,
        password_hash="not-used-by-role-check",
        role=UserRole.ACCOUNT_HOLDER,
        status=UserStatus.ACTIVE,
    )
    admin_only = require_roles(UserRole.ADMIN)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
            "http_version": "1.1",
        }
    )

    with test_session_factory() as session:
        with pytest.raises(HTTPException) as error:
            admin_only(user, request, session)

    assert error.value.status_code == 403
    with test_session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "AUTHORIZATION_REJECTED",
                AuditEvent.actor_user_id == user.id,
            )
        )
        assert event is not None
        assert event.details == {
            "method": "POST",
            "path": "/api/v1/admin",
            "reason": "insufficient_role",
        }
