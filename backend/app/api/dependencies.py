from collections.abc import Callable
from typing import Annotated, NoReturn
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.user import User, UserRole, UserStatus
from app.repositories.users import get_user_by_id
from app.services.audit import add_audit_event

_bearer_scheme = HTTPBearer(auto_error=False)


def _reject_authentication(db: Session, request: Request, reason: str) -> NoReturn:
    add_audit_event(
        db,
        actor_user_id=None,
        event_type="AUTHENTICATION_REJECTED",
        outcome="REJECTED",
        details={"method": request.method, "path": request.url.path, "reason": reason},
    )
    db.commit()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        _reject_authentication(db, request, "missing_credentials")

    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.InvalidTokenError:
        _reject_authentication(db, request, "invalid_token")

    subject = payload.get("sub")
    if not isinstance(subject, str):
        _reject_authentication(db, request, "invalid_subject")
    try:
        user_id = UUID(subject)
    except ValueError:
        _reject_authentication(db, request, "invalid_subject")

    user = get_user_by_id(db, user_id)
    if user is None or user.status is UserStatus.DISABLED:
        _reject_authentication(db, request, "user_unavailable")
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
        request: Request,
        db: Annotated[Session, Depends(get_db)],
    ) -> User:
        if current_user.role not in roles:
            add_audit_event(
                db,
                actor_user_id=current_user.id,
                event_type="AUTHORIZATION_REJECTED",
                outcome="REJECTED",
                details={
                    "method": request.method,
                    "path": request.url.path,
                    "reason": "insufficient_role",
                },
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_checker
