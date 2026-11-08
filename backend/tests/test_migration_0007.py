from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from app.core.config import get_migration_database_url

_MIGRATION_REVISION = "20261108_0006"
_STATE_TABLE = "migration_0007_legacy_email_verification_state"


@pytest.fixture
def migration_engine() -> Iterator[Engine]:
    migration_url = get_migration_database_url()
    if migration_url is None:
        pytest.fail("MIGRATION_DATABASE_URL is required for migration tests")

    url = make_url(migration_url)
    if (
        url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.database != "ledgerline"
        or url.port != 5433
    ):
        pytest.fail(
            "Migration tests are restricted to the local ledgerline database "
            "on loopback port 5433"
        )

    schema = f"ledgerline_migration_0007_test_{uuid4().hex}"
    root_engine = create_engine(migration_url, pool_pre_ping=True)
    schema_engine = create_engine(
        migration_url,
        connect_args={"options": f"-c search_path={schema}"},
        pool_pre_ping=True,
    )
    try:
        with root_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                text(f'GRANT USAGE ON SCHEMA "{schema}" TO ledgerline_app')
            )
        with schema_engine.connect() as connection:
            if connection.scalar(text("SELECT current_user")) == "ledgerline_app":
                pytest.fail("Migration tests require the local migration-owner role")
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, _MIGRATION_REVISION)
            connection.commit()
        yield schema_engine
    finally:
        schema_engine.dispose()
        with root_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        root_engine.dispose()


def _run_migration(engine: Engine, operation: str, revision: str) -> None:
    with engine.connect() as connection:
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        getattr(command, operation)(config, revision)
        connection.commit()


def test_legacy_backfill_is_cleared_without_changing_other_auth_data(
    migration_engine: Engine,
) -> None:
    legacy_timestamp = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
    verified_timestamp = datetime(2026, 11, 8, 10, 1, tzinfo=timezone.utc)
    legacy_unverified_id = uuid4()
    legacy_reverified_id = uuid4()
    already_otp_verified_id = uuid4()
    still_unverified_id = uuid4()
    password_hash = "synthetic-password-hash"

    with migration_engine.begin() as connection:
        for user_id, email, verified_at in (
            (legacy_unverified_id, "legacy-one@example.test", legacy_timestamp),
            (legacy_reverified_id, "legacy-two@example.test", legacy_timestamp),
            (already_otp_verified_id, "verified@example.test", verified_timestamp),
            (still_unverified_id, "unverified@example.test", None),
        ):
            connection.execute(
                text(
                    """
                    INSERT INTO users
                        (id, email, password_hash, email_verified_at, role, status,
                         created_at, updated_at)
                    VALUES
                        (:id, :email, :password_hash, :verified_at,
                         'ACCOUNT_HOLDER', 'ACTIVE', now(), now())
                    """
                ),
                {
                    "id": user_id,
                    "email": email,
                    "password_hash": password_hash,
                    "verified_at": verified_at,
                },
            )

        connection.execute(
            text(
                """
                INSERT INTO audit_events
                    (id, actor_user_id, event_type, outcome, details, created_at)
                VALUES
                    (:id, :user_id, 'EMAIL_OTP_VERIFIED', 'SUCCEEDED', '{}'::jsonb, :created_at)
                """
            ),
            {
                "id": uuid4(),
                "user_id": already_otp_verified_id,
                "created_at": verified_timestamp,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO user_identities (id, user_id, provider, subject)
                VALUES (:id, :user_id, 'google', 'synthetic-google-subject')
                """
            ),
            {"id": uuid4(), "user_id": legacy_unverified_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO email_otp_challenges
                    (id, user_id, code_digest, expires_at, attempt_count, last_sent_at,
                     send_window_started_at, send_count, consumed_at, created_at)
                VALUES
                    (:id, :user_id, :digest, :expires_at, 0, :sent_at, :sent_at,
                     1, NULL, :sent_at)
                """
            ),
            {
                "id": uuid4(),
                "user_id": legacy_unverified_id,
                "digest": "d" * 64,
                "expires_at": legacy_timestamp,
                "sent_at": legacy_timestamp,
            },
        )

    _run_migration(migration_engine, "upgrade", "head")

    with migration_engine.begin() as connection:
        values = {
            row.id: (row.email_verified_at, row.password_hash)
            for row in connection.execute(
                text("SELECT id, email_verified_at, password_hash FROM users")
            )
        }
        assert values[legacy_unverified_id][0] is None
        assert values[legacy_reverified_id][0] is None
        assert values[already_otp_verified_id][0] == verified_timestamp
        assert values[still_unverified_id][0] is None
        assert all(row[1] == password_hash for row in values.values())
        assert connection.scalar(
            text(f"SELECT count(*) FROM {_STATE_TABLE}")
        ) == 2
        assert connection.scalar(
            text("SELECT count(*) FROM user_identities")
        ) == 1
        assert connection.scalar(
            text("SELECT count(*) FROM email_otp_challenges")
        ) == 1
        identity = connection.execute(
            text(
                """
                SELECT user_id, provider, subject
                FROM user_identities
                """
            )
        ).one()
        assert tuple(identity) == (
            legacy_unverified_id,
            "google",
            "synthetic-google-subject",
        )
        challenge = connection.execute(
            text(
                """
                SELECT user_id, code_digest, attempt_count, expires_at
                FROM email_otp_challenges
                """
            )
        ).one()
        assert tuple(challenge) == (
            legacy_unverified_id,
            "d" * 64,
            0,
            legacy_timestamp,
        )

        connection.execute(
            text(
                """
                UPDATE users
                SET email_verified_at = :verified_at
                WHERE id = :user_id
                """
            ),
            {"user_id": legacy_reverified_id, "verified_at": verified_timestamp},
        )
        connection.execute(
            text(
                """
                INSERT INTO audit_events
                    (id, actor_user_id, event_type, outcome, details, created_at)
                VALUES
                    (:id, :user_id, 'EMAIL_OTP_VERIFIED', 'SUCCEEDED', '{}'::jsonb, :created_at)
                """
            ),
            {
                "id": uuid4(),
                "user_id": legacy_reverified_id,
                "created_at": verified_timestamp,
            },
        )

    _run_migration(migration_engine, "downgrade", _MIGRATION_REVISION)

    with migration_engine.connect() as connection:
        restored = dict(
            connection.execute(
                text("SELECT id, email_verified_at FROM users")
            ).all()
        )
        assert restored[legacy_unverified_id] == legacy_timestamp
        assert restored[legacy_reverified_id] == verified_timestamp
        assert restored[already_otp_verified_id] == verified_timestamp
        assert restored[still_unverified_id] is None
        assert connection.scalar(
            text(
                """
                SELECT to_regclass(:table_name) IS NULL
                """
            ),
            {"table_name": _STATE_TABLE},
        )
