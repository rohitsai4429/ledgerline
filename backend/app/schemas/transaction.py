from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.transaction import (
    JournalTransactionStatus,
    JournalTransactionType,
    LedgerEntryType,
)

MAX_AMOUNT_PAISE = 9_223_372_036_854_775_807


class DepositRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    amount_paise: int = Field(strict=True, gt=0, le=MAX_AMOUNT_PAISE)


class WithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    amount_paise: int = Field(strict=True, gt=0, le=MAX_AMOUNT_PAISE)


class TransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: UUID
    destination_account_id: UUID
    amount_paise: int = Field(strict=True, gt=0, le=MAX_AMOUNT_PAISE)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_type: JournalTransactionType
    status: JournalTransactionStatus
    amount_paise: int
    currency: str
    source_account_id: UUID | None
    destination_account_id: UUID | None
    related_transaction_id: UUID | None
    created_at: datetime


class StatementEntry(BaseModel):
    transaction_id: UUID
    transaction_type: JournalTransactionType
    related_transaction_id: UUID | None
    created_at: datetime
    entry_type: LedgerEntryType
    amount_paise: int
    balance_after_paise: int


class AccountStatementResponse(BaseModel):
    account_id: UUID
    currency: Literal["INR"]
    opening_balance_paise: int
    closing_balance_paise: int
    entries: list[StatementEntry]


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID
    journal_transaction_id: UUID | None
    event_type: str
    outcome: str
    details: dict[str, object]
    created_at: datetime


class StatementQuery(BaseModel):
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
