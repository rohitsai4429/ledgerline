from __future__ import annotations

from getpass import getpass
from uuid import UUID, uuid4

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import ArgumentError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User, UserRole, UserStatus
from app.services.audit import add_audit_event

DEFAULT_DATABASE_NAME = "ledgerline"
RUNTIME_ROLE = "ledgerline_app"
_email_adapter = TypeAdapter(EmailStr)


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    try:
        return str(_email_adapter.validate_python(email)).lower()
    except ValidationError:
        raise ValueError("Enter a valid email address") from None


def parse_operator_role(value: str) -> UserRole:
    try:
        role = UserRole(value.strip().upper())
    except ValueError:
        raise ValueError("Role must be ADMIN or AUDITOR") from None
    if role not in (UserRole.ADMIN, UserRole.AUDITOR):
        raise ValueError("Role must be ADMIN or AUDITOR")
    return role


def validate_migration_url(value: str) -> URL:
    try:
        url = make_url(value)
    except ArgumentError:
        raise ValueError("Enter a valid PostgreSQL connection URL") from None
    driver_name = url.drivername.split("+", 1)[0]
    if (
        driver_name != "postgresql"
        or not url.username
        or url.username == RUNTIME_ROLE
        or not url.database
        or url.query.get("sslmode") not in {"require", "verify-full"}
        or "-pooler." in (url.host or "").lower()
    ):
        raise ValueError(
            "Use a TLS-enabled direct PostgreSQL URL for the privileged migration "
            "role on the target database"
        )
    return url


def create_operator_user(
    engine: Engine,
    *,
    email: str,
    role: UserRole,
    password: str,
) -> UUID:
    email = normalize_email(email)
    if role not in (UserRole.ADMIN, UserRole.AUDITOR):
        raise ValueError("Only ADMIN or AUDITOR users can be bootstrapped")
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain between 12 and 128 characters")

    user_id = uuid4()
    with Session(engine) as session:
        existing_user = session.scalar(
            select(User.id).where(func.lower(func.trim(User.email)) == email)
        )
        if existing_user is not None:
            raise ValueError("A user with this email already exists")

        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=hash_password(password),
                role=role,
                status=UserStatus.ACTIVE,
            )
        )
        session.flush()
        add_audit_event(
            session,
            actor_user_id=None,
            event_type="PRIVILEGED_USER_BOOTSTRAPPED",
            outcome="SUCCEEDED",
            details={"email": email, "role": role.value},
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if session.scalar(
                select(User.id).where(func.lower(func.trim(User.email)) == email)
            ) is not None:
                raise ValueError("A user with this email already exists") from None
            raise

    return user_id


def main() -> None:
    migration_url = validate_migration_url(
        getpass("Direct Neon migration DATABASE_URL: ")
    )
    role = parse_operator_role(input("Application role (ADMIN or AUDITOR): "))
    email = normalize_email(input("Operator email: "))
    password = getpass("Operator password (12-128 characters): ")
    if password != getpass("Confirm operator password: "):
        raise ValueError("Passwords do not match")

    engine = create_engine(migration_url, pool_pre_ping=True, hide_parameters=True)
    try:
        try:
            user_id = create_operator_user(
                engine,
                email=email,
                role=role,
                password=password,
            )
        except SQLAlchemyError as error:
            raise RuntimeError(
                "Operator bootstrap database operation failed "
                f"({type(error).__name__}); details suppressed to protect credentials"
            ) from None
    finally:
        engine.dispose()

    print(f"Created {role.value} user {email} ({user_id}).")


if __name__ == "__main__":
    main()
