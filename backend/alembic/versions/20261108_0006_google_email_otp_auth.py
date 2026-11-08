"""Add Google identities and email OTP authentication.

Revision ID: 20261108_0006
Revises: 20261107_0005
Create Date: 2026-11-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261108_0006"
down_revision: Union[str, None] = "20261107_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NULL"),
            nullable=True,
        ),
    )
    op.create_table(
        "user_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("provider = 'google'", name="ck_user_identities_provider"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_identities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "subject",
            name="uq_user_identities_provider_subject",
        ),
        sa.UniqueConstraint(
            "provider",
            "user_id",
            name="uq_user_identities_provider_user",
        ),
        schema=None,
    )
    op.create_index(
        "ix_user_identities_user_id",
        "user_identities",
        ["user_id"],
    )
    op.create_table(
        "email_otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.SmallInteger(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_google_subject", sa.String(length=255), nullable=True),
        sa.Column("pending_google_email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 5",
            name="ck_email_otp_challenges_attempt_count",
        ),
        sa.CheckConstraint(
            "send_count BETWEEN 1 AND 5",
            name="ck_email_otp_challenges_send_count",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_email_otp_challenges_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_email_otp_challenges_user_id"),
    )
    op.create_index(
        "ix_email_otp_challenges_expires_at",
        "email_otp_challenges",
        ["expires_at"],
    )

    for table in ("user_identities", "email_otp_challenges"):
        op.execute(sa.text(f"REVOKE ALL ON {schema}.{table} FROM PUBLIC"))
    op.execute(
        sa.text(
            f"GRANT SELECT (id, user_id, provider, subject, created_at) "
            f"ON {schema}.user_identities TO {runtime_role}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT INSERT (id, user_id, provider, subject) "
            f"ON {schema}.user_identities TO {runtime_role}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT SELECT (id, user_id, code_digest, expires_at, attempt_count, "
            f"last_sent_at, send_window_started_at, send_count, consumed_at, "
            f"pending_google_subject, pending_google_email, created_at) "
            f"ON {schema}.email_otp_challenges TO {runtime_role}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT INSERT (id, user_id, code_digest, expires_at, attempt_count, "
            f"last_sent_at, send_window_started_at, send_count, consumed_at, "
            f"pending_google_subject, pending_google_email) "
            f"ON {schema}.email_otp_challenges TO {runtime_role}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT UPDATE (code_digest, expires_at, attempt_count, last_sent_at, "
            f"send_window_started_at, send_count, consumed_at, "
            f"pending_google_subject, pending_google_email) "
            f"ON {schema}.email_otp_challenges TO {runtime_role}"
        )
    )
    op.execute(
        sa.text(
            f"GRANT UPDATE (email_verified_at, updated_at) "
            f"ON {schema}.users TO {runtime_role}"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    schema = _quoted_schema()
    runtime_role = bind.dialect.identifier_preparer.quote("ledgerline_app")
    google_only_users = bind.scalar(
        sa.text(f"SELECT count(*) FROM {schema}.users WHERE password_hash IS NULL")
    )
    if google_only_users:
        raise RuntimeError(
            "Cannot downgrade Google authentication while passwordless users exist"
        )
    op.drop_index("ix_email_otp_challenges_expires_at", table_name="email_otp_challenges")
    op.drop_table("email_otp_challenges")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    op.execute(
        sa.text(
            f"REVOKE UPDATE (updated_at) ON {schema}.users FROM {runtime_role}"
        )
    )
    op.drop_column("users", "email_verified_at")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
