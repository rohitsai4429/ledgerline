from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.account import AccountStatus


class AccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_number: str
    owner_user_id: UUID
    balance_paise: int
    status: AccountStatus
    ledger_account_id: UUID
    created_at: datetime
    updated_at: datetime


class AccountStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AccountStatus
