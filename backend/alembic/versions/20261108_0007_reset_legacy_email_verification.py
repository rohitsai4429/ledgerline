"""Reset email verification values written by the 0006 legacy backfill.

Revision ID: 20261108_0007
Revises: 20261108_0006
Create Date: 2026-11-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261108_0007"
down_revision: Union[str, None] = "20261108_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATE_TABLE = "migration_0007_legacy_email_verification_state"


def _quoted_schema() -> str:
    bind = op.get_bind()
    schema = bind.scalar(sa.text("SELECT current_schema()"))
    if schema is None:
        raise RuntimeError("The migration connection has no active schema")
    return bind.dialect.identifier_preparer.quote(schema)


def upgrade() -> None:
    bind = op.get_bind()
    schema = _quoted_schema()
    runtime_role = bind.dialect.identifier_preparer.quote("ledgerline_app")

    op.create_table(
        _STATE_TABLE,
        sa.Column("user_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(sa.text(f"LOCK TABLE {schema}.users IN EXCLUSIVE MODE"))
    op.execute(
        sa.text(
            f"""
            INSERT INTO {schema}.{_STATE_TABLE} (user_id, email_verified_at)
            SELECT u.id, u.email_verified_at
            FROM {schema}.users AS u
            WHERE u.email_verified_at IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM {schema}.audit_events AS a
                  WHERE a.actor_user_id = u.id
                    AND a.event_type = 'EMAIL_OTP_VERIFIED'
                    AND a.outcome = 'SUCCEEDED'
              )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE {schema}.users AS u
            SET email_verified_at = NULL
            FROM {schema}.{_STATE_TABLE} AS saved
            WHERE u.id = saved.user_id
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON TABLE {schema}.{_STATE_TABLE} "
            f"FROM PUBLIC, {runtime_role}"
        )
    )


def downgrade() -> None:
    schema = _quoted_schema()
    op.execute(
        sa.text(
            f"""
            UPDATE {schema}.users AS u
            SET email_verified_at = saved.email_verified_at
            FROM {schema}.{_STATE_TABLE} AS saved
            WHERE u.id = saved.user_id
              AND u.email_verified_at IS NULL
            """
        )
    )
    op.drop_table(_STATE_TABLE)
