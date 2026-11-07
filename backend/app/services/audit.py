from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.transaction import AuditEvent


def add_audit_event(
    db: Session,
    *,
    actor_user_id: UUID | None,
    event_type: str,
    outcome: str,
    details: dict[str, Any],
    journal_transaction_id: UUID | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            journal_transaction_id=journal_transaction_id,
            event_type=event_type,
            outcome=outcome,
            details=details,
        )
    )
