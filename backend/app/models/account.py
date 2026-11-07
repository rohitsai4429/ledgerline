from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class LedgerAccountKind(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    DEPOSIT_CLEARING = "DEPOSIT_CLEARING"
    WITHDRAWAL_CLEARING = "WITHDRAWAL_CLEARING"


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'CUSTOMER' AND owner_user_id IS NOT NULL AND system_code IS NULL) "
            "OR (kind IN ('DEPOSIT_CLEARING', 'WITHDRAWAL_CLEARING') "
            "AND owner_user_id IS NULL AND system_code IS NOT NULL)",
            name="ck_ledger_accounts_owner_kind",
        ),
        CheckConstraint("currency = 'INR'", name="ck_ledger_accounts_currency_inr"),
        Index("ix_ledger_accounts_owner_user_id", "owner_user_id"),
        Index("uq_ledger_accounts_system_code", "system_code", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    kind: Mapped[LedgerAccountKind] = mapped_column(
        Enum(
            LedgerAccountKind,
            name="ledger_account_kind",
            values_callable=lambda kind_enum: [kind.value for kind in kind_enum],
        ),
        nullable=False,
        server_default=LedgerAccountKind.CUSTOMER.value,
    )
    system_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        server_default=text("NULL"),
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        server_default="INR",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    owner: Mapped[User | None] = relationship(back_populates="ledger_accounts")
    account: Mapped[Account | None] = relationship(
        back_populates="ledger_account",
        uselist=False,
    )


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance_paise >= 0", name="ck_accounts_balance_nonnegative"),
        CheckConstraint(
            "length(account_number) = 12 AND substr(account_number, 1, 2) = 'LL'",
            name="ck_accounts_account_number_format",
        ),
        Index("uq_accounts_account_number", "account_number", unique=True),
        Index("ix_accounts_owner_user_id", "owner_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_number: Mapped[str] = mapped_column(String(12), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ledger_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ledger_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    balance_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    status: Mapped[AccountStatus] = mapped_column(
        Enum(
            AccountStatus,
            name="account_status",
            values_callable=lambda status_enum: [status.value for status in status_enum],
        ),
        nullable=False,
        server_default=AccountStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner: Mapped[User] = relationship(back_populates="accounts")
    ledger_account: Mapped[LedgerAccount] = relationship(back_populates="account")
