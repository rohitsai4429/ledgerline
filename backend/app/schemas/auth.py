from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.user import UserRole, UserStatus

Password = Annotated[str, Field(min_length=12, max_length=128)]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Password

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: Annotated[str, Field(min_length=1, max_length=8192)]
    confirm_account_link: bool = False


class OtpChallengeResponse(BaseModel):
    status: Literal["OTP_REQUIRED"] = "OTP_REQUIRED"
    challenge_id: UUID
    expires_in_seconds: int
    resend_after_seconds: int
    message: str


class GoogleLinkConfirmationResponse(BaseModel):
    status: Literal["LINK_CONFIRMATION_REQUIRED"] = "LINK_CONFIRMATION_REQUIRED"
    message: str


class OtpVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    code: Annotated[str, Field(pattern=r"^\d{8}$")]


class OtpResendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID


class OtpResendResponse(BaseModel):
    challenge_id: UUID
    retry_after_seconds: int
    message: str


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
