from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.services.audit import add_audit_event
from app.models.user import User, UserRole, UserStatus
from app.repositories.users import get_user_by_email


class DuplicateEmailError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class DisabledUserError(Exception):
    pass


def register_user(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    if get_user_by_email(db, normalized_email) is not None:
        add_audit_event(
            db,
            actor_user_id=None,
            event_type="REGISTRATION_REJECTED",
            outcome="REJECTED",
            details={"reason": "duplicate_email"},
        )
        db.commit()
        raise DuplicateEmailError

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
    )
    try:
        db.add(user)
        db.flush()
        add_audit_event(
            db,
            actor_user_id=user.id,
            event_type="USER_REGISTERED",
            outcome="SUCCEEDED",
            details={"role": user.role.value},
        )
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError as error:
        db.rollback()
        if get_user_by_email(db, normalized_email) is not None:
            add_audit_event(
                db,
                actor_user_id=None,
                event_type="REGISTRATION_REJECTED",
                outcome="REJECTED",
                details={"reason": "duplicate_email"},
            )
            db.commit()
            raise DuplicateEmailError from error
        raise


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email.strip().lower())
    if user is None or not verify_password(password, user.password_hash):
        add_audit_event(
            db,
            actor_user_id=None,
            event_type="LOGIN_REJECTED",
            outcome="REJECTED",
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise InvalidCredentialsError
    if user.status is UserStatus.DISABLED:
        add_audit_event(
            db,
            actor_user_id=None,
            event_type="LOGIN_REJECTED",
            outcome="REJECTED",
            details={"reason": "user_disabled"},
        )
        db.commit()
        raise DisabledUserError
    add_audit_event(
        db,
        actor_user_id=user.id,
        event_type="LOGIN_SUCCEEDED",
        outcome="SUCCEEDED",
        details={},
    )
    db.commit()
    return user
