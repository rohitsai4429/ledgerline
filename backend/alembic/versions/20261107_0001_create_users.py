"""Create users for authentication.

Revision ID: 20261107_0001
Revises:
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = postgresql.ENUM(
    "ADMIN",
    "ACCOUNT_HOLDER",
    "AUDITOR",
    name="user_role",
    create_type=False,
)
user_status = postgresql.ENUM(
    "ACTIVE",
    "DISABLED",
    name="user_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "ADMIN",
        "ACCOUNT_HOLDER",
        "AUDITOR",
        name="user_role",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "ACTIVE",
        "DISABLED",
        name="user_status",
    ).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("status", user_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_users_email_normalized",
        "users",
        [sa.text("lower(trim(email))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_normalized", table_name="users")
    op.drop_table("users")
    user_status.drop(op.get_bind(), checkfirst=True)
    user_role.drop(op.get_bind(), checkfirst=True)
