from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from argon2 import PasswordHasher
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.api.dependencies import require_roles
from app.core.config import Settings, get_settings
from app.core.security import create_access_token, hash_password
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models.auth import EmailOtpChallenge, UserIdentity
from app.models.transaction import AuditEvent
from app.models.user import User, UserRole, UserStatus
from app.services import google_auth, otp

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
def otp_codes(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    codes: dict[str, list[str]] = {}
    monkeypatch.setattr(
        otp,
        "get_settings",
        lambda: SimpleNamespace(otp_hmac_secret=SecretStr("test-otp-secret-" + "x" * 32)),
    )

    def capture_email(email: str, code: str) -> None:
        codes.setdefault(email, []).append(code)

    monkeypatch.setattr(otp, "send_otp_email", capture_email)
    return codes


@pytest.fixture
def client(test_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_and_verify(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    email: str = TEST_EMAIL,
) -> User:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 202, response.json()
    assert "access_token" not in response.json()
    challenge_id = response.json()["challenge_id"]
    code = otp_codes[email][-1]
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": code},
    )
    assert verified.status_code == 200
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        challenge = session.scalar(
            select(EmailOtpChallenge).where(EmailOtpChallenge.user_id == user.id)
        )
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        session.commit()
        session.expunge(user)
        return user


def test_registration_creates_hashed_password_and_otp_without_jwt(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  HOLDER@Example.COM  ", "password": TEST_PASSWORD},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "OTP_REQUIRED"
    assert "access_token" not in body
    assert otp_codes[TEST_EMAIL]
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == TEST_EMAIL))
        challenge = session.scalar(select(EmailOtpChallenge))
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "USER_REGISTERED")
        )
        assert user is not None
        assert user.email_verified_at is None
        assert PasswordHasher().verify(user.password_hash, TEST_PASSWORD)
        assert challenge is not None
        assert challenge.code_digest != otp_codes[TEST_EMAIL][-1]
        assert otp_codes[TEST_EMAIL][-1] not in repr(challenge)
        assert event is not None
    assert otp_codes[TEST_EMAIL][-1] not in caplog.text

    protected = client.get("/api/v1/auth/me")
    assert protected.status_code == 401


def test_registration_duplicate_does_not_disclose_account_existence(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    first = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    existing_codes = len(otp_codes[TEST_EMAIL])
    second = client.post(
        "/api/v1/auth/register",
        json={"email": "HOLDER@example.com", "password": TEST_PASSWORD},
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["message"] == second.json()["message"]
    assert len(otp_codes[TEST_EMAIL]) == existing_codes
    with test_session_factory() as session:
        assert len(list(session.scalars(select(User)))) == 1


def test_registration_rejects_privileged_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "role": UserRole.ADMIN.value,
        },
    )
    assert response.status_code == 422


def test_otp_secret_rejects_example_placeholder() -> None:
    with pytest.raises(ValidationError):
        Settings(
            jwt_secret_key=SecretStr("test-jwt-secret-" + "x" * 32),
            otp_hmac_secret=SecretStr("CHANGE_ME_GENERATE_AT_LEAST_32_RANDOM_BYTES"),
        )


def test_password_login_requires_otp_before_issuing_jwt(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email.upper(), "password": TEST_PASSWORD},
    )
    assert response.status_code == 202
    assert "access_token" not in response.json()
    code = otp_codes[user.email][-1]
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": response.json()["challenge_id"], "code": code},
    )
    assert verified.status_code == 200
    replay = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": response.json()["challenge_id"],
            "code": code,
        },
    )
    assert replay.status_code == 400
    token_data = verified.json()
    claims = jwt.decode(
        token_data["access_token"],
        get_settings().jwt_secret_key.get_secret_value(),
        algorithms=[get_settings().jwt_algorithm],
    )
    assert claims["sub"] == str(user.id)
    assert claims["role"] == UserRole.ACCOUNT_HOLDER.value


def test_legacy_user_must_verify_email_before_access(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    legacy_password_hash = hash_password(TEST_PASSWORD)
    legacy_user = User(
        email=TEST_EMAIL,
        password_hash=legacy_password_hash,
        email_verified_at=None,
    )
    with test_session_factory() as session:
        session.add(legacy_user)
        session.commit()
        session.refresh(legacy_user)
        legacy_user_id = legacy_user.id

    existing_token = create_access_token(legacy_user_id, UserRole.ACCOUNT_HOLDER)
    protected_before_verification = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"******"},
    )
    assert protected_before_verification.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert login.status_code == 202
    assert "access_token" not in login.json()
    assert otp_codes[TEST_EMAIL]
    with test_session_factory() as session:
        user = session.get(User, legacy_user_id)
        assert user is not None
        assert user.password_hash == legacy_password_hash
        assert user.email_verified_at is None

    verification = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": login.json()["challenge_id"],
            "code": otp_codes[TEST_EMAIL][-1],
        },
    )
    assert verification.status_code == 200
    assert "access_token" in verification.json()
    verified_token = verification.json()["access_token"]

    protected_after_verification = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {verified_token}"},
    )
    assert protected_after_verification.status_code == 200
    assert protected_after_verification.json()["id"] == str(legacy_user_id)


def test_invalid_password_does_not_send_otp(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
    before = len(otp_codes[user.email])
    response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "not the password"},
    )
    assert response.status_code == 401
    assert len(otp_codes[user.email]) == before


def test_otp_attempt_limit_expiry_and_single_use(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    challenge_id = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    ).json()["challenge_id"]
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/otp/verify",
            json={"challenge_id": challenge_id, "code": "00000000"},
        )
        assert response.status_code == 400
    with test_session_factory() as session:
        challenge = session.get(EmailOtpChallenge, UUID(challenge_id))
        assert challenge is not None
        assert challenge.attempt_count == 5
        assert challenge.consumed_at is not None

    valid_code = otp_codes[TEST_EMAIL][-1]
    replay = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": challenge_id, "code": valid_code},
    )
    assert replay.status_code == 400


def test_expired_otp_is_rejected(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    challenge_id = UUID(response.json()["challenge_id"])
    with test_session_factory() as session:
        challenge = session.get(EmailOtpChallenge, challenge_id)
        assert challenge is not None
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    response = client.post(
        "/api/v1/auth/otp/verify",
        json={"challenge_id": str(challenge_id), "code": otp_codes[TEST_EMAIL][-1]},
    )
    assert response.status_code == 400


def test_resend_cooldown_and_persistent_send_limit(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    challenge_id = UUID(response.json()["challenge_id"])
    initial_count = len(otp_codes[TEST_EMAIL])
    cooled_down = client.post(
        "/api/v1/auth/otp/resend",
        json={"challenge_id": str(challenge_id)},
    )
    assert cooled_down.status_code == 202
    assert len(otp_codes[TEST_EMAIL]) == initial_count

    with test_session_factory() as session:
        challenge = session.get(EmailOtpChallenge, challenge_id)
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        challenge.send_count = 5
        challenge.send_window_started_at = datetime.now(timezone.utc)
        session.commit()

    limited = client.post(
        "/api/v1/auth/otp/resend",
        json={"challenge_id": str(challenge_id)},
    )
    assert limited.status_code == 429
    assert len(otp_codes[TEST_EMAIL]) == initial_count


def test_google_new_user_gets_otp_and_identity(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_auth,
        "verify_google_credential",
        lambda _credential: ("google-subject-1", "google@example.com"),
    )
    response = client.post(
        "/api/v1/auth/google",
        json={"credential": "signed-google-token"},
    )
    assert response.status_code == 202, response.json()
    assert response.json()["status"] == "OTP_REQUIRED"
    assert "access_token" not in response.json()
    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "google@example.com"))
        identity = session.scalar(select(UserIdentity))
        assert user is not None
        assert user.password_hash is None
        assert user.role is UserRole.ACCOUNT_HOLDER
        assert identity is not None
        assert identity.provider == "google"
        assert identity.subject == "google-subject-1"
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": response.json()["challenge_id"],
            "code": otp_codes["google@example.com"][-1],
        },
    )
    assert verified.status_code == 200


def test_google_matching_email_requires_explicit_link_then_otp(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    user_id = None
    with test_session_factory() as session:
        user_id = session.scalar(select(User.id).where(User.email == TEST_EMAIL))
    assert user_id is not None
    initial_sends = len(otp_codes[TEST_EMAIL])
    monkeypatch.setattr(
        google_auth,
        "verify_google_credential",
        lambda _credential: ("google-subject-link", TEST_EMAIL),
    )
    not_confirmed = client.post(
        "/api/v1/auth/google",
        json={"credential": "signed-google-token"},
    )
    assert not_confirmed.json()["status"] == "LINK_CONFIRMATION_REQUIRED"
    assert len(otp_codes[TEST_EMAIL]) == initial_sends

    with test_session_factory() as session:
        challenge = session.scalar(select(EmailOtpChallenge))
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        session.commit()
    confirmed = client.post(
        "/api/v1/auth/google",
        json={"credential": "signed-google-token", "confirm_account_link": True},
    )
    assert confirmed.status_code == 202
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": confirmed.json()["challenge_id"],
            "code": otp_codes[TEST_EMAIL][-1],
        },
    )
    assert verified.status_code == 200
    with test_session_factory() as session:
        identity = session.scalar(select(UserIdentity))
        assert identity is not None
        assert identity.user_id == user_id
        assert identity.subject == "google-subject-link"


def test_existing_google_subject_is_never_reassigned(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = register_and_verify(
        client,
        test_session_factory,
        otp_codes,
        "first@example.com",
    )
    second = register_and_verify(
        client,
        test_session_factory,
        otp_codes,
        "second@example.com",
    )
    with test_session_factory() as session:
        session.add(
            UserIdentity(
                user_id=first.id,
                provider="google",
                subject="already-linked",
            )
        )
        session.commit()
    monkeypatch.setattr(
        google_auth,
        "verify_google_credential",
        lambda _credential: ("already-linked", second.email),
    )
    response = client.post(
        "/api/v1/auth/google",
        json={"credential": "signed-google-token", "confirm_account_link": True},
    )
    assert response.status_code == 202
    challenge_id = response.json()["challenge_id"]
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": challenge_id,
            "code": otp_codes[first.email][-1],
        },
    )
    assert verified.status_code == 200
    claims = jwt.decode(
        verified.json()["access_token"],
        get_settings().jwt_secret_key.get_secret_value(),
        algorithms=[get_settings().jwt_algorithm],
    )
    assert claims["sub"] == str(first.id)
    with test_session_factory() as session:
        assert len(list(session.scalars(select(UserIdentity)))) == 1


@pytest.mark.parametrize(
    ("claim_change", "verification_error"),
    [
        ({"iss": "attacker.example"}, None),
        ({"email_verified": False}, None),
        (None, ValueError("wrong audience")),
        (None, ValueError("expired token")),
    ],
)
def test_google_claim_validation(
    monkeypatch: pytest.MonkeyPatch,
    claim_change: dict[str, object] | None,
    verification_error: Exception | None,
) -> None:
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "sub": "google-subject",
        "email": "google@example.com",
        "email_verified": True,
    }
    if claim_change:
        claims.update(claim_change)

    def verify(*_args, **_kwargs):
        if verification_error is not None:
            raise verification_error
        return claims

    monkeypatch.setattr(
        google_auth,
        "get_settings",
        lambda: SimpleNamespace(google_client_id="configured-client-id"),
    )
    monkeypatch.setattr(google_auth.id_token, "verify_oauth2_token", verify)
    if claim_change or verification_error is not None:
        with pytest.raises(google_auth.InvalidGoogleCredential):
            google_auth.verify_google_credential("credential")
    else:
        assert google_auth.verify_google_credential("credential") == (
            "google-subject",
            "google@example.com",
        )


def test_invalid_google_credential_is_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        google_auth,
        "verify_google_credential",
        lambda _credential: (_ for _ in ()).throw(google_auth.InvalidGoogleCredential()),
    )
    response = client.post(
        "/api/v1/auth/google",
        json={"credential": "invalid"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Google credential could not be verified"}


def test_disabled_users_and_existing_roles_remain_enforced(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
) -> None:
    for role in UserRole:
        user = User(
            id=uuid4(),
            email=f"{role.value.lower()}@example.com",
            password_hash=hash_password(TEST_PASSWORD),
            email_verified_at=datetime.now(timezone.utc),
            role=role,
            status=UserStatus.ACTIVE,
        )
        with test_session_factory() as session:
            session.add(user)
            session.commit()
            token = create_access_token(user.id, user.role)
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == role.value

    with test_session_factory() as session:
        disabled = User(
            email="disabled@example.com",
            password_hash=hash_password(TEST_PASSWORD),
            email_verified_at=datetime.now(timezone.utc),
            status=UserStatus.DISABLED,
        )
        session.add(disabled)
        session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@example.com", "password": TEST_PASSWORD},
    )
    assert response.status_code == 403


def test_expired_jwt_is_rejected(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
    token = create_access_token(
        user.id,
        user.role,
        expires_delta=timedelta(seconds=-1),
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("missing_claim", ["exp", "iat"])
def test_jwt_requires_issued_and_expiration_claims(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    missing_claim: str,
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
    claims: dict[str, object] = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    claims.pop(missing_claim)
    token = jwt.encode(
        claims,
        get_settings().jwt_secret_key.get_secret_value(),
        algorithm=get_settings().jwt_algorithm,
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "attack",
    ["malformed", "tampered", "wrong_algorithm", "missing_sub"],
)
def test_invalid_jwt_variants_are_rejected(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
    attack: str,
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
    token = create_access_token(user.id, user.role)
    if attack == "malformed":
        token = "not-a-jwt"
    elif attack == "tampered":
        token = f"{token.rsplit('.', 1)[0]}.{'a' * 40}"
    elif attack == "wrong_algorithm":
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            get_settings().jwt_secret_key.get_secret_value(),
            algorithm="HS512",
        )
    else:
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


def test_current_user_returns_safe_profile(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
    token = create_access_token(user.id, user.role)
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert response.json()["email"] == user.email
    assert response.json()["role"] == UserRole.ACCOUNT_HOLDER.value
    assert "password_hash" not in response.json()


def test_account_holder_is_denied_admin_authorization(
    client: TestClient,
    test_session_factory: sessionmaker[Session],
    otp_codes: dict[str, list[str]],
) -> None:
    user = register_and_verify(client, test_session_factory, otp_codes)
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
