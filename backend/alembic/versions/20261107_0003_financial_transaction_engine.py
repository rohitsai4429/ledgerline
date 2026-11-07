"""Add immutable double-entry transaction infrastructure.

Revision ID: 20261107_0003
Revises: 20261107_0002
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0003"
down_revision: Union[str, None] = "20261107_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ledger_account_kind = postgresql.ENUM(
    "CUSTOMER",
    "DEPOSIT_CLEARING",
    "WITHDRAWAL_CLEARING",
    name="ledger_account_kind",
    create_type=False,
)
journal_transaction_type = postgresql.ENUM(
    "DEPOSIT",
    "WITHDRAWAL",
    "TRANSFER",
    "REVERSAL",
    name="journal_transaction_type",
    create_type=False,
)
journal_transaction_status = postgresql.ENUM(
    "POSTING",
    "POSTED",
    name="journal_transaction_status",
    create_type=False,
)
ledger_entry_type = postgresql.ENUM(
    "DEBIT",
    "CREDIT",
    name="ledger_entry_type",
    create_type=False,
)
idempotency_outcome = postgresql.ENUM(
    "SUCCEEDED",
    "REJECTED",
    name="idempotency_outcome",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (
        ledger_account_kind,
        journal_transaction_type,
        journal_transaction_status,
        ledger_entry_type,
        idempotency_outcome,
    ):
        enum.create(bind, checkfirst=True)

    op.alter_column("ledger_accounts", "owner_user_id", nullable=True)
    op.add_column(
        "ledger_accounts",
        sa.Column(
            "kind",
            ledger_account_kind,
            server_default=sa.text("'CUSTOMER'"),
            nullable=False,
        ),
    )
    op.add_column("ledger_accounts", sa.Column("system_code", sa.String(length=50), nullable=True))
    op.add_column(
        "ledger_accounts",
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
    )
    op.create_check_constraint(
        "ck_ledger_accounts_owner_kind",
        "ledger_accounts",
        "(kind = 'CUSTOMER' AND owner_user_id IS NOT NULL AND system_code IS NULL) "
        "OR (kind IN ('DEPOSIT_CLEARING', 'WITHDRAWAL_CLEARING') "
        "AND owner_user_id IS NULL AND system_code IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_ledger_accounts_currency_inr",
        "ledger_accounts",
        "currency = 'INR'",
    )
    op.create_index(
        "uq_ledger_accounts_system_code",
        "ledger_accounts",
        ["system_code"],
        unique=True,
    )

    op.create_table(
        "journal_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", journal_transaction_type, nullable=False),
        sa.Column(
            "status",
            journal_transaction_status,
            server_default=sa.text("'POSTING'"),
            nullable=False,
        ),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("destination_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_paise > 0", name="ck_journal_transactions_amount_positive"),
        sa.CheckConstraint("currency = 'INR'", name="ck_journal_transactions_currency_inr"),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(
            ["source_account_id"],
            ["accounts.id"],
            name="fk_journal_transactions_source_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_account_id"],
            ["accounts.id"],
            name="fk_journal_transactions_destination_account_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_transaction_id"],
            ["journal_transactions.id"],
            name="fk_journal_txn_reversal",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            ["users.id"],
            name="fk_journal_transactions_initiated_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "related_transaction_id",
            name="uq_journal_transactions_related_transaction_id",
        ),
    )
    op.create_index(
        "ix_journal_transactions_created_at",
        "journal_transactions",
        ["created_at"],
    )
    op.create_index(
        "ix_journal_transactions_source_account_id",
        "journal_transactions",
        ["source_account_id"],
    )
    op.create_index(
        "ix_journal_transactions_destination_account_id",
        "journal_transactions",
        ["destination_account_id"],
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("journal_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", ledger_entry_type, nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_paise > 0", name="ck_ledger_entries_amount_positive"),
        sa.CheckConstraint("currency = 'INR'", name="ck_ledger_entries_currency_inr"),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"],
            ["journal_transactions.id"],
            name="fk_ledger_entries_journal_transaction_id_journal_transactions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"],
            ["ledger_accounts.id"],
            name="fk_ledger_entries_ledger_account_id_ledger_accounts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ledger_entries_ledger_account_id",
        "ledger_entries",
        ["ledger_account_id"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", idempotency_outcome, nullable=False),
        sa.Column("journal_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(outcome = 'SUCCEEDED' AND journal_transaction_id IS NOT NULL AND result_code IS NULL) "
            "OR (outcome = 'REJECTED' AND journal_transaction_id IS NULL AND result_code IS NOT NULL)",
            name="ck_idempotency_records_result",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_idempotency_records_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"],
            ["journal_transactions.id"],
            name="fk_idempotency_txn",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "journal_transaction_id",
            name="uq_idempotency_records_journal_transaction_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_idempotency_records_user_key",
        ),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("journal_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('SUCCEEDED', 'REJECTED')",
            name="ck_audit_events_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_audit_events_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"],
            ["journal_transactions.id"],
            name="fk_audit_events_journal_transaction_id_journal_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_actor_created_at",
        "audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_events_journal_transaction_id",
        "audit_events",
        ["journal_transaction_id"],
    )

    op.execute(
        """
        INSERT INTO ledger_accounts (id, owner_user_id, kind, system_code, currency)
        VALUES
            ('00000000-0000-4000-8000-000000000001', NULL, 'DEPOSIT_CLEARING',
             'deposit-clearing-inr', 'INR'),
            ('00000000-0000-4000-8000-000000000002', NULL, 'WITHDRAWAL_CLEARING',
             'withdrawal-clearing-inr', 'INR')
        """
    )

    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_journal_mutation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'journal transactions cannot be deleted';
            END IF;
            IF OLD.status <> 'POSTING'
               OR NEW.status <> 'POSTED'
               OR (to_jsonb(NEW) - 'status') IS DISTINCT FROM (to_jsonb(OLD) - 'status') THEN
                RAISE EXCEPTION 'posted journal transactions are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_ledger_account_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger account identity is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_accounts_immutable
        BEFORE UPDATE OR DELETE ON ledger_accounts
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_ledger_account_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_account_identity() RETURNS trigger AS $$
        BEGIN
            IF OLD.owner_user_id IS DISTINCT FROM NEW.owner_user_id
               OR OLD.ledger_account_id IS DISTINCT FROM NEW.ledger_account_id THEN
                RAISE EXCEPTION 'account ownership and ledger linkage are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_accounts_identity_immutable
        BEFORE UPDATE OF owner_user_id, ledger_account_id ON accounts
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_account_identity()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_journal_transactions_immutable
        BEFORE UPDATE OR DELETE ON journal_transactions
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_journal_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_entry_insert() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM journal_transactions
                WHERE id = NEW.journal_transaction_id AND status = 'POSTING'
            ) THEN
                RAISE EXCEPTION 'entries may only be added while a journal is posting';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_entry_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger entries are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_insert
        BEFORE INSERT ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_entry_insert()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_ledger_entries_immutable
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_entry_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_validate_posted_journal() RETURNS trigger AS $$
        DECLARE
            journal journal_transactions%ROWTYPE;
            entry_count integer;
            debit_count integer;
            credit_count integer;
            debit_total bigint;
            credit_total bigint;
            min_amount bigint;
            max_amount bigint;
            currency_count integer;
            valid_mapping_count integer;
        BEGIN
            SELECT * INTO journal
            FROM journal_transactions
            WHERE id = NEW.id;
            IF NOT FOUND THEN
                RETURN NULL;
            END IF;
            IF journal.status <> 'POSTED' THEN
                RAISE EXCEPTION 'journal must be posted before commit';
            END IF;

            SELECT count(*),
                   count(*) FILTER (WHERE entry_type = 'DEBIT'),
                   count(*) FILTER (WHERE entry_type = 'CREDIT'),
                   sum(amount_paise) FILTER (WHERE entry_type = 'DEBIT'),
                   sum(amount_paise) FILTER (WHERE entry_type = 'CREDIT'),
                   min(amount_paise),
                   max(amount_paise),
                   count(DISTINCT currency)
            INTO entry_count, debit_count, credit_count, debit_total, credit_total,
                 min_amount, max_amount, currency_count
            FROM ledger_entries
            WHERE journal_transaction_id = journal.id;

            IF entry_count <> 2 OR debit_count <> 1 OR credit_count <> 1
               OR debit_total <> credit_total OR min_amount <> journal.amount_paise
               OR max_amount <> journal.amount_paise OR currency_count <> 1 THEN
                RAISE EXCEPTION 'posted journal must contain exactly two equal balanced entries';
            END IF;

            IF journal.transaction_type = 'DEPOSIT' THEN
                SELECT count(*) INTO valid_mapping_count
                FROM ledger_entries e
                JOIN ledger_accounts la ON la.id = e.ledger_account_id
                JOIN accounts a ON a.id = journal.destination_account_id
                WHERE e.journal_transaction_id = journal.id
                  AND ((e.entry_type = 'DEBIT' AND la.kind = 'DEPOSIT_CLEARING'
                        AND la.system_code = 'deposit-clearing-inr')
                    OR (e.entry_type = 'CREDIT' AND a.ledger_account_id = e.ledger_account_id));
            ELSIF journal.transaction_type = 'WITHDRAWAL' THEN
                SELECT count(*) INTO valid_mapping_count
                FROM ledger_entries e
                JOIN ledger_accounts la ON la.id = e.ledger_account_id
                JOIN accounts a ON a.id = journal.source_account_id
                WHERE e.journal_transaction_id = journal.id
                  AND ((e.entry_type = 'DEBIT' AND a.ledger_account_id = e.ledger_account_id)
                    OR (e.entry_type = 'CREDIT' AND la.kind = 'WITHDRAWAL_CLEARING'
                        AND la.system_code = 'withdrawal-clearing-inr'));
            ELSIF journal.transaction_type = 'TRANSFER' THEN
                SELECT count(*) INTO valid_mapping_count
                FROM ledger_entries e
                JOIN accounts source_account ON source_account.id = journal.source_account_id
                JOIN accounts destination_account ON destination_account.id = journal.destination_account_id
                WHERE e.journal_transaction_id = journal.id
                  AND ((e.entry_type = 'DEBIT'
                        AND source_account.ledger_account_id = e.ledger_account_id)
                    OR (e.entry_type = 'CREDIT'
                        AND destination_account.ledger_account_id = e.ledger_account_id));
            ELSE
                SELECT count(*) INTO valid_mapping_count
                FROM ledger_entries reversal
                JOIN ledger_entries original
                  ON original.journal_transaction_id = journal.related_transaction_id
                 AND original.ledger_account_id = reversal.ledger_account_id
                 AND original.amount_paise = reversal.amount_paise
                 AND original.currency = reversal.currency
                 AND original.entry_type <> reversal.entry_type
                JOIN journal_transactions original_journal
                  ON original_journal.id = journal.related_transaction_id
                WHERE reversal.journal_transaction_id = journal.id
                  AND original_journal.transaction_type <> 'REVERSAL'
                  AND original_journal.status = 'POSTED'
                  AND journal.amount_paise = original_journal.amount_paise
                  AND journal.currency = original_journal.currency
                  AND journal.source_account_id IS NOT DISTINCT FROM original_journal.source_account_id
                  AND journal.destination_account_id IS NOT DISTINCT FROM original_journal.destination_account_id;
            END IF;

            IF valid_mapping_count <> 2 THEN
                RAISE EXCEPTION 'journal entries do not match the transaction parties and type';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_journal_transactions_balanced
        AFTER INSERT OR UPDATE ON journal_transactions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledgerline_validate_posted_journal()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_validate_account_balance() RETURNS trigger AS $$
        DECLARE
            ledger_id uuid;
            ledger_balance bigint;
        BEGIN
            SELECT ledger_account_id INTO ledger_id FROM accounts WHERE id = NEW.id;
            SELECT coalesce(sum(CASE WHEN entry_type = 'CREDIT' THEN amount_paise
                                     ELSE -amount_paise END), 0)
            INTO ledger_balance
            FROM ledger_entries WHERE ledger_account_id = ledger_id;
            IF NEW.balance_paise <> ledger_balance THEN
                RAISE EXCEPTION 'account balance must equal its posted ledger balance';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_accounts_balance_matches_ledger
        AFTER UPDATE OF balance_paise ON accounts
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledgerline_validate_account_balance()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_guard_idempotency_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'idempotency records are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_idempotency_records_immutable
        BEFORE UPDATE OR DELETE ON idempotency_records
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_idempotency_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION ledgerline_validate_ledger_balance() RETURNS trigger AS $$
        DECLARE
            cached_balance bigint;
            ledger_balance bigint;
        BEGIN
            SELECT balance_paise INTO cached_balance
            FROM accounts WHERE ledger_account_id = NEW.ledger_account_id;
            IF NOT FOUND THEN
                RETURN NULL;
            END IF;
            SELECT coalesce(sum(CASE WHEN entry_type = 'CREDIT' THEN amount_paise
                                     ELSE -amount_paise END), 0)
            INTO ledger_balance
            FROM ledger_entries WHERE ledger_account_id = NEW.ledger_account_id;
            IF cached_balance <> ledger_balance THEN
                RAISE EXCEPTION 'ledger entries must reconcile to the account balance';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_ledger_entries_balance_matches_account
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledgerline_validate_ledger_balance()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION ledgerline_guard_audit_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM journal_transactions)
               OR EXISTS (SELECT 1 FROM audit_events)
               OR EXISTS (SELECT 1 FROM idempotency_records) THEN
                RAISE EXCEPTION 'cannot downgrade financial transaction data';
            END IF;
        END;
        $$
        """
    )

    for trigger in (
        "trg_audit_events_immutable",
        "trg_idempotency_records_immutable",
        "trg_ledger_entries_balance_matches_account",
        "trg_accounts_balance_matches_ledger",
        "trg_accounts_identity_immutable",
        "trg_ledger_accounts_immutable",
        "trg_journal_transactions_balanced",
        "trg_ledger_entries_immutable",
        "trg_ledger_entries_insert",
        "trg_journal_transactions_immutable",
    ):
        table = (
            "audit_events"
            if trigger == "trg_audit_events_immutable"
            else "idempotency_records"
            if trigger == "trg_idempotency_records_immutable"
            else "accounts"
            if trigger in (
                "trg_accounts_balance_matches_ledger",
                "trg_accounts_identity_immutable",
            )
            else "ledger_accounts"
            if trigger == "trg_ledger_accounts_immutable"
            else "journal_transactions"
            if trigger in ("trg_journal_transactions_balanced", "trg_journal_transactions_immutable")
            else "ledger_entries"
        )
        op.execute(f"DROP TRIGGER {trigger} ON {table}")

    for function in (
        "ledgerline_guard_audit_mutation",
        "ledgerline_guard_idempotency_mutation",
        "ledgerline_guard_account_identity",
        "ledgerline_guard_ledger_account_mutation",
        "ledgerline_validate_ledger_balance",
        "ledgerline_validate_account_balance",
        "ledgerline_validate_posted_journal",
        "ledgerline_guard_entry_mutation",
        "ledgerline_guard_entry_insert",
        "ledgerline_guard_journal_mutation",
    ):
        op.execute(f"DROP FUNCTION {function}()")

    op.drop_index("ix_audit_events_journal_transaction_id", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("idempotency_records")
    op.drop_index("ix_ledger_entries_ledger_account_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_journal_transactions_destination_account_id", table_name="journal_transactions")
    op.drop_index("ix_journal_transactions_source_account_id", table_name="journal_transactions")
    op.drop_index("ix_journal_transactions_created_at", table_name="journal_transactions")
    op.drop_table("journal_transactions")
    op.execute(
        """
        DELETE FROM ledger_accounts
        WHERE system_code IN ('deposit-clearing-inr', 'withdrawal-clearing-inr')
        """
    )
    op.drop_index("uq_ledger_accounts_system_code", table_name="ledger_accounts")
    op.drop_constraint("ck_ledger_accounts_currency_inr", "ledger_accounts", type_="check")
    op.drop_constraint("ck_ledger_accounts_owner_kind", "ledger_accounts", type_="check")
    op.drop_column("ledger_accounts", "currency")
    op.drop_column("ledger_accounts", "system_code")
    op.drop_column("ledger_accounts", "kind")
    op.alter_column("ledger_accounts", "owner_user_id", nullable=False)

    for enum in (
        idempotency_outcome,
        ledger_entry_type,
        journal_transaction_status,
        journal_transaction_type,
        ledger_account_kind,
    ):
        enum.drop(op.get_bind(), checkfirst=True)
