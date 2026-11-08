from __future__ import annotations

from getpass import getpass

from psycopg import Error as PsycopgError
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

DEFAULT_DATABASE_NAME = "ledgerline"
RUNTIME_ROLE = "ledgerline_app"
REQUIRED_RUNTIME_ROLE_ATTRIBUTES = {
    "can_login": True,
    "is_superuser": False,
    "can_create_db": False,
    "can_create_roles": False,
    "inherits_privileges": False,
    "can_replication": False,
    "can_bypass_rls": False,
}


def validate_migration_url(value: str) -> URL:
    try:
        migration_url = make_url(value)
    except ArgumentError:
        raise ValueError("Enter a valid PostgreSQL connection URL") from None
    driver_name = migration_url.drivername.split("+", 1)[0]
    if (
        driver_name != "postgresql"
        or not migration_url.username
        or migration_url.username == RUNTIME_ROLE
        or not migration_url.database
        or migration_url.query.get("sslmode") not in {"require", "verify-full"}
        or "-pooler." in (migration_url.host or "").lower()
    ):
        raise ValueError(
            "Use a TLS-enabled direct PostgreSQL URL for the Neon migration owner "
            "on the target database"
        )
    return migration_url


def validate_existing_runtime_role(connection) -> None:
    row = connection.execute(
        text(
            """
            SELECT rolcanlogin AS can_login,
                   rolsuper AS is_superuser,
                   rolcreatedb AS can_create_db,
                   rolcreaterole AS can_create_roles,
                   rolinherit AS inherits_privileges,
                   rolreplication AS can_replication,
                   rolbypassrls AS can_bypass_rls
            FROM pg_roles
            WHERE rolname = :role_name
            """
        ),
        {"role_name": RUNTIME_ROLE},
    ).one_or_none()
    if row is None:
        return

    mismatches = [
        (name, expected, value)
        for name, expected, value in (
            ("LOGIN", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["can_login"], row.can_login),
            ("NOSUPERUSER", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["is_superuser"], row.is_superuser),
            ("NOCREATEDB", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["can_create_db"], row.can_create_db),
            ("NOCREATEROLE", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["can_create_roles"], row.can_create_roles),
            ("NOINHERIT", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["inherits_privileges"], row.inherits_privileges),
            ("NOREPLICATION", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["can_replication"], row.can_replication),
            ("NOBYPASSRLS", REQUIRED_RUNTIME_ROLE_ATTRIBUTES["can_bypass_rls"], row.can_bypass_rls),
        )
        if value != expected
    ]
    if mismatches:
        details = ", ".join(f"{flag}={value}" for flag, _, value in mismatches)
        raise RuntimeError(
            f"Existing {RUNTIME_ROLE} role is not restricted correctly in pg_roles: {details}. "
            "Do not alter SUPERUSER or recreate the role; fix the existing role attributes manually."
        )


def main() -> None:
    migration_url = validate_migration_url(
        getpass("Direct Neon migration DATABASE_URL: ")
    )

    password = getpass("New ledgerline_app password (minimum 32 characters): ")
    if len(password) < 32:
        raise ValueError("The runtime database password must be at least 32 characters")
    if password != getpass("Confirm ledgerline_app password: "):
        raise ValueError("Runtime database passwords do not match")

    engine = create_engine(migration_url, pool_pre_ping=True, hide_parameters=True)
    try:
        try:
            with engine.begin() as connection:
                identity = connection.execute(
                    text(
                        """
                        SELECT current_user AS current_user_name,
                               current_database() AS database_name,
                               role.rolsuper AS is_superuser,
                               role.rolcreaterole AS can_create_roles,
                               CASE
                                   WHEN EXISTS (
                                       SELECT 1 FROM pg_roles
                                       WHERE rolname = 'neon_superuser'
                                   )
                                   THEN pg_has_role(
                                       current_user, 'neon_superuser', 'USAGE'
                                   )
                                   ELSE FALSE
                               END AS has_neon_admin_membership,
                               pg_has_role(
                                   current_user, namespace.nspowner, 'USAGE'
                               ) AS owns_public_schema
                        FROM pg_roles AS role
                        CROSS JOIN pg_namespace AS namespace
                        WHERE role.rolname = current_user
                          AND namespace.nspname = 'public'
                        """
                    )
                ).one()
                if identity.current_user_name == RUNTIME_ROLE:
                    raise RuntimeError(
                        "Connect as the Neon migration owner, not the runtime role"
                    )
                database_name = migration_url.database or DEFAULT_DATABASE_NAME
                if identity.database_name != database_name:
                    raise RuntimeError(
                        f"Connect as the Neon migration owner to database {database_name}"
                    )
                if not identity.owns_public_schema:
                    raise RuntimeError("The migration role must own the public schema")
                if (
                    not identity.is_superuser
                    and not identity.can_create_roles
                    and not identity.has_neon_admin_membership
                ):
                    raise RuntimeError(
                        "The database owner cannot create or manage roles; "
                        "do not broaden its privileges to bypass this check"
                    )
                migration_role = connection.dialect.identifier_preparer.quote(
                    identity.current_user_name
                )

                role_exists = connection.scalar(
                    text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"),
                    {"role": RUNTIME_ROLE},
                )
                if role_exists:
                    validate_existing_runtime_role(connection)
                else:
                    driver_connection = connection.connection.driver_connection
                    cursor = driver_connection.cursor()
                    try:
                        cursor.execute(
                            'CREATE ROLE "{}" LOGIN PASSWORD %s NOSUPERUSER '
                            'NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS'.format(
                                RUNTIME_ROLE
                            ),
                            (password,),
                        )
                    finally:
                        cursor.close()

                connection.execute(
                    text(
                        """
                        DO $$
                        DECLARE granted_role name;
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
                quoted_database_name = connection.dialect.identifier_preparer.quote(
                    database_name
                )
                quoted_role_name = connection.dialect.identifier_preparer.quote(
                    RUNTIME_ROLE
                )
                connection.execute(
                    text(
                        f"GRANT CONNECT ON DATABASE {quoted_database_name} "
                        f"TO {quoted_role_name}"
                    )
                )
                connection.execute(
                    text(
                        f"REVOKE CREATE ON DATABASE {quoted_database_name} "
                        f"FROM {quoted_role_name}"
                    )
                )
                connection.execute(
                    text("REVOKE CREATE ON SCHEMA public FROM ledgerline_app")
                )
                connection.execute(
                    text("GRANT USAGE ON SCHEMA public TO ledgerline_app")
                )
                has_schema_create = connection.scalar(
                    text(
                        "SELECT has_schema_privilege("
                        "'ledgerline_app', 'public', 'CREATE')"
                    )
                )
                if has_schema_create:
                    raise RuntimeError(
                        "ledgerline_app still has effective CREATE privilege on public; "
                        "remove its source grant explicitly before continuing"
                    )
                for object_type in ("TABLES", "SEQUENCES", "FUNCTIONS"):
                    connection.execute(
                        text(
                            f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_role} "
                            "IN SCHEMA public "
                            f"REVOKE ALL ON {object_type} FROM ledgerline_app"
                        )
                    )
                connection.execute(
                    text(
                        f"ALTER DEFAULT PRIVILEGES FOR ROLE {migration_role} "
                        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
                    )
                )
        except (PsycopgError, SQLAlchemyError) as error:
            raise RuntimeError(
                "Role provisioning database operation failed "
                f"({type(error).__name__}); details suppressed to protect credentials"
            ) from None
    finally:
        engine.dispose()

    print(f"Provisioned restricted ledgerline_app role for database {migration_url.database}.")


if __name__ == "__main__":
    main()
