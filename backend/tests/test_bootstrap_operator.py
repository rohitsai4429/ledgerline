from pathlib import Path

import pytest

from scripts.bootstrap_operator import (
    normalize_email,
    parse_operator_role,
    validate_migration_url,
)
from scripts.provision_runtime_role import (
    validate_migration_url as validate_provisioning_url,
)
from app.models.user import UserRole


def test_normalize_email_uses_validated_lowercase_address() -> None:
    assert normalize_email("  Operator@Example.com ") == "operator@example.com"


def test_parse_operator_role_accepts_only_privileged_roles() -> None:
    assert parse_operator_role("admin") is UserRole.ADMIN
    assert parse_operator_role("AUDITOR") is UserRole.AUDITOR
    with pytest.raises(ValueError, match="ADMIN or AUDITOR"):
        parse_operator_role("ACCOUNT_HOLDER")


def test_migration_url_requires_tls_and_direct_database_endpoint() -> None:
    url = validate_migration_url(
        "postgresql://owner@ep-example.us-east-2.aws.neon.tech/"
        "neondb?sslmode=require"
    )
    assert url.database == "neondb"

    with pytest.raises(ValueError, match="direct"):
        validate_migration_url(
            "postgresql://owner@ep-example-pooler.us-east-2.aws.neon.tech/"
            "neondb?sslmode=require"
        )

    with pytest.raises(ValueError, match="direct"):
        validate_migration_url(
            "postgresql://ledgerline_app@ep-example.us-east-2.aws.neon.tech/"
            "neondb?sslmode=require"
        )


def test_role_provisioner_requires_tls_and_direct_owner_connection() -> None:
    url = validate_provisioning_url(
        "postgresql://owner@ep-example.us-east-2.aws.neon.tech/"
        "neondb?sslmode=verify-full"
    )
    assert url.database == "neondb"

    with pytest.raises(ValueError, match="direct"):
        validate_provisioning_url(
            "postgresql://owner@ep-example-pooler.us-east-2.aws.neon.tech/"
            "neondb?sslmode=require"
        )

    with pytest.raises(ValueError, match="TLS-enabled"):
        validate_provisioning_url(
            "postgresql://owner@ep-example.us-east-2.aws.neon.tech/neondb"
        )


def test_invalid_connection_url_errors_do_not_echo_input() -> None:
    invalid_url = "malformed-connection-secret"
    for validator in (validate_migration_url, validate_provisioning_url):
        with pytest.raises(ValueError) as error:
            validator(invalid_url)
        assert invalid_url not in str(error.value)


def test_migration_0005_does_not_attempt_prohibited_alter_role() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20261107_0005_runtime_privilege_hardening.py"
    )
    migration_text = migration_path.read_text(encoding="utf-8")

    assert "ALTER ROLE ledgerline_app WITH LOGIN NOSUPERUSER" not in migration_text
    assert "ALTER ROLE ledgerline_app" not in migration_text
