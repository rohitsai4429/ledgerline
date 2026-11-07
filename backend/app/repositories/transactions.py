from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.transaction import AuditEvent, JournalTransaction


def get_transaction(db: Session, transaction_id: UUID) -> JournalTransaction | None:
    return db.get(JournalTransaction, transaction_id)


def list_transactions(
    db: Session,
    account_ids: list[UUID] | None,
    limit: int,
    offset: int,
) -> list[JournalTransaction]:
    statement = select(JournalTransaction).order_by(
        JournalTransaction.created_at.desc(),
        JournalTransaction.id.desc(),
    )
    if account_ids is not None:
        if not account_ids:
            return []
        statement = statement.where(
            (JournalTransaction.source_account_id.in_(account_ids))
            | (JournalTransaction.destination_account_id.in_(account_ids))
        )
    return list(db.scalars(statement.limit(limit).offset(offset)).all())


def list_audit_events(
    db: Session,
    actor_user_id: UUID | None,
    start: datetime | None,
    limit: int,
    offset: int,
) -> list[AuditEvent]:
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    if actor_user_id is not None:
        statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
    if start is not None:
        statement = statement.where(AuditEvent.created_at >= start)
    return list(db.scalars(statement.limit(limit).offset(offset)).all())
