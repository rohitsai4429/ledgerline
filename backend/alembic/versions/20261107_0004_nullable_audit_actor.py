"""Allow audit events for unauthenticated attempts.

Revision ID: 20261107_0004
Revises: 20261107_0003
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0004"
down_revision: Union[str, None] = "20261107_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "audit_events",
        "actor_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM audit_events WHERE actor_user_id IS NULL) THEN "
            "RAISE EXCEPTION 'Cannot require audit actors while anonymous audit events exist'; "
            "END IF; "
            "END $$"
        )
    )
    op.alter_column(
        "audit_events",
        "actor_user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
