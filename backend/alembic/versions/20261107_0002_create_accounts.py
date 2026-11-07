"""Create customer and ledger accounts.

Revision ID: 20261107_0002
Revises: 20261107_0001
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0002"
down_revision: Union[str, None] = "20261107_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

account_status = postgresql.ENUM(
    "ACTIVE",
    "FROZEN",
    "CLOSED",
    name="account_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(
        "ACTIVE",
        "FROZEN",
        "CLOSED",
        name="account_status",
    ).create(bind, checkfirst=True)

    op.create_table(
        "ledger_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_ledger_accounts_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ledger_accounts_owner_user_id",
        "ledger_accounts",
        ["owner_user_id"],
    )

    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_number", sa.String(length=12), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "balance_paise",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "status",
            account_status,
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "balance_paise >= 0",
            name="ck_accounts_balance_nonnegative",
        ),
        sa.CheckConstraint(
            "length(account_number) = 12 AND substr(account_number, 1, 2) = 'LL'",
            name="ck_accounts_account_number_format",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            ["ledger_accounts.id"],
            name="fk_accounts_ledger_account_id_ledger_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_accounts_owner_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ledger_account_id",
            name="uq_accounts_ledger_account_id",
        ),
    )
    op.create_index("ix_accounts_owner_user_id", "accounts", ["owner_user_id"])
    op.create_index(
        "uq_accounts_account_number",
        "accounts",
        ["account_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_accounts_account_number", table_name="accounts")
    op.drop_index("ix_accounts_owner_user_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_index("ix_ledger_accounts_owner_user_id", table_name="ledger_accounts")
    op.drop_table("ledger_accounts")
    account_status.drop(op.get_bind(), checkfirst=True)
