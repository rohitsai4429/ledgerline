import secrets
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import Account, AccountStatus, LedgerAccount
from app.models.user import User
from app.models.user import UserRole
from app.repositories.accounts import get_account_by_id, get_account_by_number, list_accounts


class AccountNotFoundError(Exception):
    pass


class AccountNumberGenerationError(Exception):
    pass


class ClosedAccountError(Exception):
    pass


def _new_account_number() -> str:
    return f"LL{secrets.randbelow(10**10):010d}"


def create_account(db: Session, owner: User) -> Account:
    for _ in range(5):
        account_number = _new_account_number()
        if get_account_by_number(db, account_number) is not None:
            continue

        ledger_account = LedgerAccount(owner_user_id=owner.id)
        db.add(ledger_account)
        db.flush()
        account = Account(
            account_number=account_number,
            owner_user_id=owner.id,
            ledger_account_id=ledger_account.id,
            balance_paise=0,
            status=AccountStatus.ACTIVE,
        )
        db.add(account)
        try:
            db.flush()
            db.commit()
        except IntegrityError as error:
            db.rollback()
            if get_account_by_number(db, account_number) is not None:
                continue
            raise error
        db.refresh(account)
        return account
    raise AccountNumberGenerationError


def get_account(
    db: Session,
    account_id: uuid.UUID,
    viewer: User,
) -> Account:
    account = get_account_by_id(db, account_id)
    if account is None or (
        viewer.role is UserRole.ACCOUNT_HOLDER and account.owner_user_id != viewer.id
    ):
        raise AccountNotFoundError
    return account


def get_accounts(db: Session, viewer: User) -> list[Account]:
    owner_user_id = viewer.id if viewer.role is UserRole.ACCOUNT_HOLDER else None
    return list_accounts(db, owner_user_id)


def update_account_status(
    db: Session,
    account_id: uuid.UUID,
    status: AccountStatus,
) -> Account:
    account = get_account_by_id(db, account_id)
    if account is None:
        raise AccountNotFoundError
    if account.status is AccountStatus.CLOSED and status is not AccountStatus.CLOSED:
        raise ClosedAccountError
    account.status = status
    db.commit()
    db.refresh(account)
    return account
