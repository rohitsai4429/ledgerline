import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.account import Account


def get_account_by_id(db: Session, account_id: uuid.UUID) -> Account | None:
    return db.scalar(
        select(Account)
        .options(joinedload(Account.ledger_account))
        .where(Account.id == account_id)
    )


def get_account_by_number(db: Session, account_number: str) -> Account | None:
    return db.scalar(select(Account).where(Account.account_number == account_number))


def list_accounts(db: Session, owner_user_id: uuid.UUID | None = None) -> list[Account]:
    statement = select(Account).options(joinedload(Account.ledger_account)).order_by(Account.created_at.desc())
    if owner_user_id is not None:
        statement = statement.where(Account.owner_user_id == owner_user_id)
    return list(db.scalars(statement).unique().all())
