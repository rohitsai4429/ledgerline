from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.engine import Connection

from app import models
from app.core.config import get_migration_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

migration_database_url = get_migration_database_url()
if migration_database_url is None:
    raise RuntimeError("MIGRATION_DATABASE_URL must be set to run Alembic migrations")

config.set_main_option(
    "sqlalchemy.url",
    migration_database_url.replace("%", "%%"),
)
target_metadata = models.Base.metadata


def include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    # PostgreSQL reflects the normalized-email index with rewritten TRIM syntax.
    if (
        type_ == "index"
        and name == "uq_users_email_normalized"
        and getattr(object_, "name", None) == name
        and (reflected or compare_to is not None)
    ):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_with_connection(connection: Connection) -> None:
    had_transaction = connection.in_transaction()
    current_user = connection.scalar(text("SELECT current_user"))
    if not had_transaction:
        connection.commit()
    if current_user == "ledgerline_app":
        raise RuntimeError("Alembic migrations must not run as ledgerline_app")

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    provided_connection = config.attributes.get("connection")
    if provided_connection is not None:
        run_with_connection(provided_connection)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        run_with_connection(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
