"""Apply least-privilege grants to the runtime database role.

Revision ID: 20261107_0005
Revises: 20261107_0004
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_0005"
down_revision: Union[str, None] = "20261107_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _schema_name() -> str:
    bind = op.get_bind()
    schema = bind.scalar(sa.text("SELECT current_schema()"))
    if schema is None:
        raise RuntimeError("The migration connection has no active schema")
    return bind.dialect.identifier_preparer.quote(schema)


def upgrade() -> None:
    bind = op.get_bind()
    schema = _schema_name()

    mismatched_ledgers = bind.scalar(
        sa.text(
            f"""
            SELECT count(*)
            FROM {schema}.ledger_accounts la
            LEFT JOIN {schema}.accounts a ON a.ledger_account_id = la.id
            WHERE la.kind = 'CUSTOMER'
              AND (a.id IS NULL OR a.owner_user_id IS DISTINCT FROM la.owner_user_id)
            """
        )
    )
    mismatched_accounts = bind.scalar(
        sa.text(
            f"""
            SELECT count(*)
            FROM {schema}.accounts a
            JOIN {schema}.ledger_accounts la ON la.id = a.ledger_account_id
            WHERE la.kind <> 'CUSTOMER'
               OR la.owner_user_id IS DISTINCT FROM a.owner_user_id
            """
        )
    )
    if mismatched_ledgers or mismatched_accounts:
        raise RuntimeError(
            "Refusing least-privilege migration: customer account and ledger ownership "
            "links are inconsistent"
        )

    op.alter_column(
        "users",
        "role",
        existing_type=sa.Enum(name="user_role"),
        server_default=sa.text("'ACCOUNT_HOLDER'"),
    )
    op.alter_column(
        "users",
        "status",
        existing_type=sa.Enum(name="user_status"),
        server_default=sa.text("'ACTIVE'"),
    )
    op.alter_column(
        "ledger_accounts",
        "system_code",
        existing_type=sa.String(length=50),
        server_default=sa.text("NULL"),
    )

    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {schema}.ledgerline_validate_customer_ledger_linkage()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
                ledger_id uuid;
                ledger_owner uuid;
                ledger_kind text;
                account_owner uuid;
            BEGIN
                IF TG_TABLE_NAME = 'ledger_accounts' THEN
                    ledger_id := NEW.id;
                ELSE
                    ledger_id := NEW.ledger_account_id;
                    account_owner := NEW.owner_user_id;
                END IF;

                SELECT la.owner_user_id, la.kind::text
                INTO ledger_owner, ledger_kind
                FROM {schema}.ledger_accounts la
                WHERE la.id = ledger_id;
                IF NOT FOUND OR ledger_kind <> 'CUSTOMER' THEN
                    RAISE EXCEPTION 'customer account must reference a customer ledger account';
                END IF;
                IF account_owner IS NOT NULL AND account_owner IS DISTINCT FROM ledger_owner THEN
                    RAISE EXCEPTION 'customer account and ledger owners must match';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM {schema}.accounts a
                    WHERE a.ledger_account_id = ledger_id
                      AND a.owner_user_id = ledger_owner
                ) THEN
                    RAISE EXCEPTION 'customer ledger account must have one matching account';
                END IF;
                RETURN NULL;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE CONSTRAINT TRIGGER trg_customer_ledger_account_link "
            f"AFTER INSERT ON {schema}.ledger_accounts "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"EXECUTE FUNCTION {schema}.ledgerline_validate_customer_ledger_linkage()"
        )
    )
    op.execute(
        sa.text(
            f"CREATE CONSTRAINT TRIGGER trg_customer_account_ledger_link "
            f"AFTER INSERT ON {schema}.accounts "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"EXECUTE FUNCTION {schema}.ledgerline_validate_customer_ledger_linkage()"
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {schema}.ledgerline_mark_journal_posted(p_journal_id uuid)
            RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {schema}
            AS $$
            BEGIN
                UPDATE {schema}.journal_transactions
                SET status = 'POSTED'
                WHERE id = p_journal_id AND status = 'POSTING';
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'journal is missing or is not in posting state';
                END IF;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION {schema}.ledgerline_mark_journal_posted(uuid) FROM PUBLIC"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE FUNCTION {schema}.ledgerline_lock_journal_for_reversal(
                p_journal_id uuid
            )
            RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = pg_catalog, {schema}
            AS $$
            BEGIN
                PERFORM 1
                FROM {schema}.journal_transactions
                WHERE id = p_journal_id
                  AND status = 'POSTED'
                  AND transaction_type <> 'REVERSAL'
                FOR UPDATE;
            END;
            $$
            """
        )
    )
    op.execute(
        sa.text(
            f"REVOKE ALL ON FUNCTION "
            f"{schema}.ledgerline_lock_journal_for_reversal(uuid) FROM PUBLIC"
        )
    )

    current_database = bind.scalar(sa.text("SELECT current_database()"))
    if current_database is None:
        raise RuntimeError("The migration connection has no active database")
    database = bind.dialect.identifier_preparer.quote(current_database)
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                granted_role name;
            BEGIN
                FOR granted_role IN
                    SELECT role.rolname
                    FROM pg_auth_members membership
                    JOIN pg_roles role ON role.oid = membership.roleid
                    WHERE membership.member = 'ledgerline_app'::regrole
                LOOP
                    EXECUTE format('REVOKE %I FROM ledgerline_app', granted_role);
                END LOOP;
            END;
            $$
            """
        )
    )
    for statement in (
        "ALTER ROLE ledgerline_app WITH NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT",
        f"REVOKE CREATE ON DATABASE {database} FROM ledgerline_app",
        f"REVOKE CREATE ON SCHEMA {schema} FROM ledgerline_app",
        f"REVOKE CREATE ON SCHEMA {schema} FROM PUBLIC",
        f"REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} FROM ledgerline_app",
        f"REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} FROM ledgerline_app",
        f"REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA {schema} FROM PUBLIC",
        f"REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA {schema} FROM ledgerline_app",
        "ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user "
        "REVOKE ALL ON TABLES FROM ledgerline_app",
        "ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user "
        "REVOKE ALL ON SEQUENCES FROM ledgerline_app",
        "ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user "
        "REVOKE ALL ON FUNCTIONS FROM ledgerline_app",
        "ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_user "
        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
        f"GRANT USAGE ON SCHEMA {schema} TO ledgerline_app",
    ):
        op.execute(sa.text(statement))

    column_privileges = {
        "users": (
            "id, email, password_hash, role, status, created_at, updated_at",
        ),
        "accounts": (
            "id, account_number, owner_user_id, ledger_account_id, balance_paise, "
            "status, created_at, updated_at",
        ),
        "ledger_accounts": (
            "id, owner_user_id, kind, system_code, currency, created_at",
        ),
        "journal_transactions": (
            "id, transaction_type, status, amount_paise, currency, source_account_id, "
            "destination_account_id, related_transaction_id, initiated_by_user_id, created_at",
        ),
        "ledger_entries": (
            "id, journal_transaction_id, ledger_account_id, entry_type, amount_paise, "
            "currency, created_at",
        ),
        "idempotency_records": (
            "id, user_id, idempotency_key, request_hash, outcome, "
            "journal_transaction_id, result_code, created_at",
        ),
        "audit_events": (
            "id, actor_user_id, journal_transaction_id, event_type, outcome, details, created_at",
        ),
    }
    for table, (columns,) in column_privileges.items():
        op.execute(
            sa.text(
                f"REVOKE INSERT ({columns}) ON {schema}.{table} FROM ledgerline_app"
            )
        )
    op.execute(
        sa.text(
            f"REVOKE UPDATE (id, account_number, owner_user_id, ledger_account_id, "
            f"balance_paise, status, created_at, updated_at) "
            f"ON {schema}.accounts FROM ledgerline_app"
        )
    )

    for statement in (
        f"GRANT SELECT ON {schema}.users, {schema}.accounts, "
        f"{schema}.ledger_accounts, {schema}.journal_transactions, "
        f"{schema}.ledger_entries, {schema}.idempotency_records, "
        f"{schema}.audit_events TO ledgerline_app",
        f"GRANT INSERT (id, email, password_hash) ON {schema}.users TO ledgerline_app",
        f"GRANT INSERT (id, account_number, owner_user_id, ledger_account_id) "
        f"ON {schema}.accounts TO ledgerline_app",
        f"GRANT UPDATE (balance_paise, status, updated_at) "
        f"ON {schema}.accounts TO ledgerline_app",
        f"GRANT INSERT (id, owner_user_id) "
        f"ON {schema}.ledger_accounts TO ledgerline_app",
        f"GRANT INSERT (id, transaction_type, amount_paise, source_account_id, "
        f"destination_account_id, related_transaction_id, initiated_by_user_id) "
        f"ON {schema}.journal_transactions TO ledgerline_app",
        f"GRANT INSERT (id, journal_transaction_id, ledger_account_id, entry_type, "
        f"amount_paise) ON {schema}.ledger_entries TO ledgerline_app",
        f"GRANT INSERT (id, user_id, idempotency_key, request_hash, outcome, "
        f"journal_transaction_id, result_code) "
        f"ON {schema}.idempotency_records TO ledgerline_app",
        f"GRANT INSERT (id, actor_user_id, journal_transaction_id, event_type, "
        f"outcome, details) ON {schema}.audit_events TO ledgerline_app",
        f"GRANT EXECUTE ON FUNCTION {schema}.ledgerline_mark_journal_posted(uuid) "
        "TO ledgerline_app",
        f"GRANT EXECUTE ON FUNCTION "
        f"{schema}.ledgerline_lock_journal_for_reversal(uuid) TO ledgerline_app",
    ):
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError(
        "Runtime privilege hardening is intentionally irreversible automatically; "
        "restore permissions only through an explicitly reviewed migration"
    )
