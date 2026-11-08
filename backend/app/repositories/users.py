from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.auth import UserIdentity


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(
        select(User).where(func.lower(func.trim(User.email)) == email.strip().lower())
    )


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.get(User, user_id)


def get_user_identity(
    db: Session,
    provider: str,
    subject: str,
) -> UserIdentity | None:
    return db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.subject == subject,
        )
    )


def add_user(db: Session, user: User) -> User:
    db.add(user)
    db.flush()
    db.commit()
    db.refresh(user)
    return user
