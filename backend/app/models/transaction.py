from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class JournalTransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER = "TRANSFER"
    REVERSAL = "REVERSAL"


class JournalTransactionStatus(str, enum.Enum):
    POSTING = "POSTING"
    POSTED = "POSTED"


class LedgerEntryType(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class IdempotencyOutcome(str, enum.Enum):
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"


class JournalTransaction(Base):
    __tablename__ = "journal_transactions"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_journal_transactions_amount_positive"),
        CheckConstraint("currency = 'INR'", name="ck_journal_transactions_currency_inr"),
        CheckConstraint(
            "(transaction_type = 'DEPOSIT' AND source_account_id IS NULL "
            "AND destination_account_id IS NOT NULL AND related_transaction_id IS NULL) "
            "OR (transaction_type = 'WITHDRAWAL' AND source_account_id IS NOT NULL "
            "AND destination_account_id IS NULL AND related_transaction_id IS NULL) "
            "OR (transaction_type = 'TRANSFER' AND source_account_id IS NOT NULL "
            "AND destination_account_id IS NOT NULL AND source_account_id <> destination_account_id "
            "AND related_transaction_id IS NULL) "
            "OR (transaction_type = 'REVERSAL' AND related_transaction_id IS NOT NULL)",
            name="ck_journal_transactions_parties",
        ),
        UniqueConstraint(
            "related_transaction_id",
            name="uq_journal_transactions_related_transaction_id",
        ),
        Index("ix_journal_transactions_created_at", "created_at"),
        Index("ix_journal_transactions_source_account_id", "source_account_id"),
        Index("ix_journal_transactions_destination_account_id", "destination_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_type: Mapped[JournalTransactionType] = mapped_column(
        Enum(
            JournalTransactionType,
            name="journal_transaction_type",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    status: Mapped[JournalTransactionStatus] = mapped_column(
        Enum(
            JournalTransactionStatus,
            name="journal_transaction_status",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
        default=JournalTransactionStatus.POSTING,
        server_default=JournalTransactionStatus.POSTING.value,
    )
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")
    source_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "accounts.id",
            name="fk_journal_transactions_source_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    destination_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "accounts.id",
            name="fk_journal_transactions_destination_account_id_accounts",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "journal_transactions.id",
            name="fk_journal_txn_reversal",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    initiated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    entries: Mapped[list[LedgerEntry]] = relationship(back_populates="journal_transaction")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_ledger_entries_amount_positive"),
        CheckConstraint("currency = 'INR'", name="ck_ledger_entries_currency_inr"),
        Index("ix_ledger_entries_ledger_account_id", "ledger_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    journal_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "journal_transactions.id",
            name="fk_ledger_entries_journal_transaction_id_journal_transactions",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    ledger_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "ledger_accounts.id",
            name="fk_ledger_entries_ledger_account_id_ledger_accounts",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        Enum(
            LedgerEntryType,
            name="ledger_entry_type",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    journal_transaction: Mapped[JournalTransaction] = relationship(back_populates="entries")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        CheckConstraint(
            "(outcome = 'SUCCEEDED' AND journal_transaction_id IS NOT NULL AND result_code IS NULL) "
            "OR (outcome = 'REJECTED' AND journal_transaction_id IS NULL AND result_code IS NOT NULL)",
            name="ck_idempotency_records_result",
        ),
        UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_idempotency_records_user_key",
        ),
        UniqueConstraint(
            "journal_transaction_id",
            name="uq_idempotency_records_journal_transaction_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[IdempotencyOutcome] = mapped_column(
        Enum(
            IdempotencyOutcome,
            name="idempotency_outcome",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    journal_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "journal_transactions.id",
            name="fk_idempotency_txn",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    result_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('SUCCEEDED', 'REJECTED')",
            name="ck_audit_events_outcome",
        ),
        Index("ix_audit_events_actor_created_at", "actor_user_id", "created_at"),
        Index("ix_audit_events_journal_transaction_id", "journal_transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    journal_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "journal_transactions.id",
            name="fk_audit_events_journal_transaction_id_journal_transactions",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
