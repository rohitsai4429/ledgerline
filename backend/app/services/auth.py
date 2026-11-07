from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole, UserStatus
from app.repositories.users import add_user, get_user_by_email


class DuplicateEmailError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class DisabledUserError(Exception):
    pass


def register_user(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    if get_user_by_email(db, normalized_email) is not None:
        raise DuplicateEmailError

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        role=UserRole.ACCOUNT_HOLDER,
        status=UserStatus.ACTIVE,
    )
    try:
        return add_user(db, user)
    except IntegrityError as error:
        db.rollback()
        if get_user_by_email(db, normalized_email) is not None:
            raise DuplicateEmailError from error
        raise


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email.strip().lower())
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    if user.status is UserStatus.DISABLED:
        raise DisabledUserError
    return user
