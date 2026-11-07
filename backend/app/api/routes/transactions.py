from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.database.session import get_db
from app.models.transaction import JournalTransaction
from app.models.user import User, UserRole
from app.schemas.transaction import (
    AccountStatementResponse,
    AuditEventResponse,
    DepositRequest,
    TransactionResponse,
    TransferRequest,
    WithdrawalRequest,
)
from app.services.transactions import (
    IdempotencyConflict,
    TransactionRejected,
    deposit as deposit_service,
    get_account_statement,
    get_audit_history,
    get_transaction_history,
    reverse_transaction as reverse_transaction_service,
    transfer as transfer_service,
    withdraw as withdrawal_service,
)

router = APIRouter(tags=["financial transactions"])


def _transaction_error(error: TransactionRejected) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _idempotency_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Idempotency key was already used with a different request",
    )


@router.post(
    "/transactions/deposits",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_deposit(
    payload: DepositRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> JournalTransaction:
    try:
        return deposit_service(
            db,
            current_user,
            payload.account_id,
            payload.amount_paise,
            idempotency_key,
        )
    except IdempotencyConflict:
        raise _idempotency_error() from None
    except TransactionRejected as error:
        raise _transaction_error(error) from None


@router.post(
    "/transactions/withdrawals",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_withdrawal(
    payload: WithdrawalRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> JournalTransaction:
    try:
        return withdrawal_service(
            db,
            current_user,
            payload.account_id,
            payload.amount_paise,
            idempotency_key,
        )
    except IdempotencyConflict:
        raise _idempotency_error() from None
    except TransactionRejected as error:
        raise _transaction_error(error) from None


@router.post(
    "/transactions/transfers",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transfer(
    payload: TransferRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> JournalTransaction:
    try:
        return transfer_service(
            db,
            current_user,
            payload.source_account_id,
            payload.destination_account_id,
            payload.amount_paise,
            idempotency_key,
        )
    except IdempotencyConflict:
        raise _idempotency_error() from None
    except TransactionRejected as error:
        raise _transaction_error(error) from None


@router.post(
    "/transactions/{transaction_id}/reverse",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_transaction(
    transaction_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
) -> JournalTransaction:
    try:
        return reverse_transaction_service(db, current_user, transaction_id, idempotency_key)
    except IdempotencyConflict:
        raise _idempotency_error() from None
    except TransactionRejected as error:
        raise _transaction_error(error) from None


@router.get("/transactions", response_model=list[TransactionResponse])
def transaction_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    account_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[JournalTransaction]:
    try:
        return get_transaction_history(db, current_user, account_id, limit, offset)
    except TransactionRejected as error:
        raise _transaction_error(error) from None


@router.get(
    "/accounts/{account_id}/statement",
    response_model=AccountStatementResponse,
)
def account_statement(
    account_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
) -> AccountStatementResponse:
    try:
        return get_account_statement(db, current_user, account_id, start, end)
    except TransactionRejected as error:
        raise _transaction_error(error) from None
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@router.get(
    "/audit-events",
    response_model=list[AuditEventResponse],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.AUDITOR))],
)
def audit_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    actor_user_id: UUID | None = None,
    start: AwareDatetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditEventResponse]:
    try:
        return get_audit_history(
            db,
            current_user,
            actor_user_id,
            start,
            limit,
            offset,
        )
    except TransactionRejected as error:
        raise _transaction_error(error) from None
