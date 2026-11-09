from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import EmailOtpChallenge, UserIdentity
from app.models.user import User, UserStatus
from app.services.audit import add_audit_event

OTP_LIFETIME = timedelta(minutes=5)
RESEND_COOLDOWN = timedelta(seconds=60)
SEND_WINDOW = timedelta(hours=1)
MAX_ATTEMPTS = 5
MAX_SENDS_PER_WINDOW = 5
OTP_REQUIRED_MESSAGE = "If this sign-in can be completed, a verification code has been sent to your email."


class OtpConfigurationError(Exception):
    pass


class OtpDeliveryError(Exception):
    pass


class OtpRateLimited(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds


class InvalidOtpError(Exception):
    pass


@dataclass(frozen=True)
class OtpIssue:
    challenge_id: UUID
    code: str | None
    expires_in_seconds: int
    resend_after_seconds: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _secret() -> bytes:
    configured = get_settings().otp_hmac_secret
    if configured is None:
        raise OtpConfigurationError
    return configured.get_secret_value().encode("utf-8")


def _digest(challenge_id: UUID, user_id: UUID, code: str) -> str:
    message = f"{challenge_id}:{user_id}:{code}".encode("utf-8")
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def send_otp_email(email: str, code: str) -> None:
    settings = get_settings()
    if not settings.otp_mailer_url or settings.otp_mailer_secret is None:
        raise OtpDeliveryError
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            response = client.post(
                settings.otp_mailer_url,
                json={
                    "secret": settings.otp_mailer_secret.get_secret_value(),
                    "email": email,
                    "code": code,
                },
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise OtpDeliveryError
    except (httpx.HTTPError, ValueError, OtpDeliveryError):
        raise OtpDeliveryError from None


def issue_challenge(
    db: Session,
    user: User,
    *,
    google_subject: str | None = None,
    google_email: str | None = None,
    challenge_id: UUID | None = None,
    resend_only: bool = False,
) -> OtpIssue:
    _secret()
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if locked_user is None or locked_user.status is UserStatus.DISABLED:
        raise InvalidOtpError
    challenge = db.scalar(
        select(EmailOtpChallenge)
        .where(EmailOtpChallenge.user_id == locked_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = _now()
    if challenge_id is not None and (
        challenge is None or challenge.id != challenge_id
    ):
        return OtpIssue(challenge_id, None, 0, int(RESEND_COOLDOWN.total_seconds()))
    if resend_only and (challenge is None or challenge.consumed_at is not None):
        return OtpIssue(challenge_id or uuid4(), None, 0, int(RESEND_COOLDOWN.total_seconds()))

    if challenge is not None:
        last_sent_at = _aware(challenge.last_sent_at)
        elapsed = now - last_sent_at
        if elapsed < RESEND_COOLDOWN:
            if not resend_only and (
                challenge.consumed_at is not None
                or challenge.pending_google_subject != google_subject
                or challenge.pending_google_email != google_email
            ):
                raise OtpRateLimited(
                    max(1, int((RESEND_COOLDOWN - elapsed).total_seconds()))
                )
            retry_after = max(1, int((RESEND_COOLDOWN - elapsed).total_seconds()))
            return OtpIssue(challenge.id, None, max(0, int((_aware(challenge.expires_at) - now).total_seconds())), retry_after)

        window_started = _aware(challenge.send_window_started_at)
        if now - window_started >= SEND_WINDOW:
            challenge.send_window_started_at = now
            challenge.send_count = 0
        elif challenge.send_count >= MAX_SENDS_PER_WINDOW:
            retry_after = max(1, int((SEND_WINDOW - (now - window_started)).total_seconds()))
            raise OtpRateLimited(retry_after)
        challenge.send_count += 1
        code = f"{secrets.randbelow(100_000_000):08d}"
        challenge.code_digest = _digest(challenge.id, locked_user.id, code)
        challenge.expires_at = now + OTP_LIFETIME
        challenge.attempt_count = 0
        challenge.last_sent_at = now
        challenge.consumed_at = None
        if not resend_only:
            challenge.pending_google_subject = google_subject
            challenge.pending_google_email = google_email
    else:
        challenge_uuid = uuid4()
        code = f"{secrets.randbelow(100_000_000):08d}"
        challenge = EmailOtpChallenge(
            id=challenge_uuid,
            user_id=locked_user.id,
            code_digest=_digest(challenge_uuid, locked_user.id, code),
            expires_at=now + OTP_LIFETIME,
            attempt_count=0,
            last_sent_at=now,
            send_window_started_at=now,
            send_count=1,
            pending_google_subject=google_subject,
            pending_google_email=google_email,
        )
        db.add(challenge)

    db.commit()
    return OtpIssue(challenge.id, code, int(OTP_LIFETIME.total_seconds()), int(RESEND_COOLDOWN.total_seconds()))


def deliver_challenge(email: str, issue: OtpIssue) -> None:
    if issue.code is not None:
        send_otp_email(email, issue.code)


def resend_challenge(db: Session, challenge_id: UUID) -> OtpIssue:
    challenge = db.scalar(
        select(EmailOtpChallenge)
        .where(EmailOtpChallenge.id == challenge_id)
    )
    if challenge is None:
        return OtpIssue(challenge_id, None, 0, int(RESEND_COOLDOWN.total_seconds()))
    user = db.get(User, challenge.user_id)
    if user is None or user.status is UserStatus.DISABLED:
        return OtpIssue(challenge_id, None, 0, int(RESEND_COOLDOWN.total_seconds()))
    return issue_challenge(db, user, challenge_id=challenge_id, resend_only=True)


def verify_challenge(db: Session, challenge_id: UUID, code: str) -> User:
    _secret()
    now = _now()
    challenge = db.scalar(
        select(EmailOtpChallenge).where(EmailOtpChallenge.id == challenge_id)
    )
    if challenge is None:
        raise InvalidOtpError
    user = db.scalar(
        select(User).where(User.id == challenge.user_id).with_for_update()
    )
    challenge = db.scalar(
        select(EmailOtpChallenge)
        .where(EmailOtpChallenge.id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        user is None
        or user.status is UserStatus.DISABLED
        or challenge is None
        or challenge.consumed_at is not None
        or _aware(challenge.expires_at) <= now
        or challenge.attempt_count >= MAX_ATTEMPTS
    ):
        db.rollback()
        raise InvalidOtpError

    expected = _digest(challenge.id, challenge.user_id, code)
    if not hmac.compare_digest(challenge.code_digest, expected):
        attempt_update = db.execute(
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.id == challenge_id,
                EmailOtpChallenge.consumed_at.is_(None),
                EmailOtpChallenge.expires_at > now,
                EmailOtpChallenge.attempt_count < MAX_ATTEMPTS,
            )
            .values(
                attempt_count=EmailOtpChallenge.attempt_count + 1,
                consumed_at=case(
                    (EmailOtpChallenge.attempt_count + 1 >= MAX_ATTEMPTS, now),
                    else_=EmailOtpChallenge.consumed_at,
                ),
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if attempt_update.rowcount != 1:
            raise InvalidOtpError
        raise InvalidOtpError

    consume = db.execute(
        update(EmailOtpChallenge)
        .where(
            EmailOtpChallenge.id == challenge_id,
            EmailOtpChallenge.consumed_at.is_(None),
            EmailOtpChallenge.expires_at > now,
            EmailOtpChallenge.attempt_count < MAX_ATTEMPTS,
        )
        .values(consumed_at=now)
        .execution_options(synchronize_session=False)
    )
    if consume.rowcount != 1:
        db.rollback()
        raise InvalidOtpError

    if challenge.pending_google_subject is not None:
        if (
            challenge.pending_google_email is None
            or user.email.strip().lower() != challenge.pending_google_email.strip().lower()
        ):
            db.rollback()
            raise InvalidOtpError
        identity = db.scalar(
            select(UserIdentity).where(
                UserIdentity.provider == "google",
                UserIdentity.subject == challenge.pending_google_subject,
            )
        )
        if identity is not None and identity.user_id != user.id:
            db.rollback()
            raise InvalidOtpError
        if identity is None:
            db.add(
                UserIdentity(
                    user_id=user.id,
                    provider="google",
                    subject=challenge.pending_google_subject,
                )
            )

    user.email_verified_at = now
    add_audit_event(
        db,
        actor_user_id=user.id,
        event_type="EMAIL_OTP_VERIFIED",
        outcome="SUCCEEDED",
        details={},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        db.execute(
            update(EmailOtpChallenge)
            .where(
                EmailOtpChallenge.id == challenge_id,
                EmailOtpChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        db.commit()
        raise InvalidOtpError from None
    db.refresh(user)
    return user
