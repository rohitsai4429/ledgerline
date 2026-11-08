from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.database.session import get_db
from app.models.account import Account, AccountStatus
from app.models.user import User, UserRole
from app.repositories.accounts import get_account_by_number
from app.schemas.account import (
    AccountCreateRequest,
    AccountResponse,
    AccountStatusUpdate,
    RecipientLookupRequest,
    RecipientLookupResponse,
)
from app.services.accounts import (
    AccountNumberGenerationError,
    AccountNotFoundError,
    ClosedAccountError,
    create_account as create_account_service,
    get_account as get_account_service,
    get_accounts as get_accounts_service,
    update_account_status,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("/recipient-lookup", response_model=RecipientLookupResponse)
def lookup_recipient_account(
    payload: RecipientLookupRequest,
    current_user: Annotated[User, Depends(require_roles(UserRole.ACCOUNT_HOLDER))],
    db: Annotated[Session, Depends(get_db)],
) -> RecipientLookupResponse:
    account = get_account_by_number(db, payload.account_number)
    if account is None or account.status is not AccountStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient account not found or unavailable",
        )

    return RecipientLookupResponse(
        destination_account_id=account.id,
        masked_account_number=f"{'*' * (len(account.account_number) - 4)}{account.account_number[-4:]}",
        status=account.status,
    )


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    current_user: Annotated[User, Depends(require_roles(UserRole.ACCOUNT_HOLDER))],
    db: Annotated[Session, Depends(get_db)],
    _payload: Annotated[AccountCreateRequest | None, Body()] = None,
) -> Account:
    if _payload is not None and _payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Account creation does not accept writable fields",
        )
    try:
        return create_account_service(db, current_user)
    except AccountNumberGenerationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to allocate an account number; please retry",
        ) from None


@router.get("", response_model=list[AccountResponse])
def list_customer_accounts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Account]:
    return get_accounts_service(db, current_user)


@router.get("/{account_id}", response_model=AccountResponse)
def get_customer_account(
    account_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Account:
    try:
        return get_account_service(db, account_id, current_user)
    except AccountNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from None


@router.patch(
    "/{account_id}/status",
    response_model=AccountResponse,
)
def set_customer_account_status(
    account_id: UUID,
    payload: AccountStatusUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    db: Annotated[Session, Depends(get_db)],
) -> Account:
    try:
        return update_account_status(db, account_id, payload.status, current_user)
    except AccountNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found") from None
    except ClosedAccountError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Closed accounts cannot be reactivated",
        ) from None
