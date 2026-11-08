from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import UserIdentity
from app.models.user import User, UserStatus
from app.repositories.users import get_user_by_email, get_user_by_id, get_user_identity
from app.services.audit import add_audit_event


class InvalidGoogleCredential(Exception):
    pass


class GoogleConfigurationError(Exception):
    pass


@dataclass(frozen=True)
class GoogleAuthStart:
    user: User | None
    subject: str | None
    email: str | None
    link_confirmation_required: bool = False


def verify_google_credential(credential: str) -> tuple[str, str]:
    client_id = get_settings().google_client_id
    if not client_id:
        raise GoogleConfigurationError
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(
            credential,
            Request(),
            audience=client_id,
        )
    except (ValueError, GoogleAuthError):
        raise InvalidGoogleCredential from None

    issuer = claims.get("iss")
    subject = claims.get("sub")
    email = claims.get("email")
    if (
        issuer not in {"accounts.google.com", "https://accounts.google.com"}
        or not isinstance(subject, str)
        or not subject
        or len(subject) > 255
        or not isinstance(email, str)
        or not email
        or len(email) > 320
        or claims.get("email_verified") is not True
    ):
        raise InvalidGoogleCredential
    return subject, email.strip().lower()


def resolve_google_user(
    db: Session,
    subject: str,
    email: str,
    *,
    confirm_account_link: bool,
) -> GoogleAuthStart:
    identity = get_user_identity(db, "google", subject)
    if identity is not None:
        user = get_user_by_id(db, identity.user_id)
        if user is None or user.status is UserStatus.DISABLED:
            raise InvalidGoogleCredential
        return GoogleAuthStart(user, None, None)

    user = get_user_by_email(db, email)
    if user is not None:
        if user.status is UserStatus.DISABLED:
            raise InvalidGoogleCredential
        if not confirm_account_link:
            return GoogleAuthStart(None, subject, email, True)
        return GoogleAuthStart(user, subject, email)

    user = User(
        email=email,
        password_hash=None,
    )
    try:
        db.add(user)
        db.flush()
        db.add(
            UserIdentity(
                user_id=user.id,
                provider="google",
                subject=subject,
            )
        )
        add_audit_event(
            db,
            actor_user_id=user.id,
            event_type="USER_REGISTERED",
            outcome="SUCCEEDED",
            details={"role": user.role.value, "auth_provider": "google"},
        )
        db.commit()
        db.refresh(user)
        return GoogleAuthStart(user, None, None)
    except IntegrityError:
        db.rollback()
        identity = get_user_identity(db, "google", subject)
        if identity is not None:
            user = get_user_by_id(db, identity.user_id)
            if user is not None and user.status is UserStatus.ACTIVE:
                return GoogleAuthStart(user, None, None)
        user = get_user_by_email(db, email)
        if user is not None and user.status is UserStatus.ACTIVE:
            if confirm_account_link:
                return GoogleAuthStart(user, subject, email)
            return GoogleAuthStart(None, subject, email, True)
        raise InvalidGoogleCredential from None
