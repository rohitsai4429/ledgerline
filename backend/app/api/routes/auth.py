from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token
from app.database.session import get_db
from app.models.auth import EmailOtpChallenge
from app.models.user import User
from app.schemas.auth import (
    GoogleLinkConfirmationResponse,
    GoogleLoginRequest,
    LoginRequest,
    OtpChallengeResponse,
    OtpResendRequest,
    OtpResendResponse,
    OtpVerifyRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    DisabledUserError,
    DuplicateEmailError,
    InvalidCredentialsError,
    authenticate_user,
    register_user,
)
from app.services import google_auth
from app.services.otp import (
    OTP_REQUIRED_MESSAGE,
    InvalidOtpError,
    OtpConfigurationError,
    OtpDeliveryError,
    OtpRateLimited,
    OtpIssue,
    deliver_challenge,
    issue_challenge,
    resend_challenge,
    verify_challenge,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _challenge_response(issue: OtpIssue) -> OtpChallengeResponse:
    return OtpChallengeResponse(
        challenge_id=issue.challenge_id,
        expires_in_seconds=issue.expires_in_seconds,
        resend_after_seconds=issue.resend_after_seconds,
        message=OTP_REQUIRED_MESSAGE,
    )


def _issue_for_user(
    db: Session,
    user: User,
    *,
    google_subject: str | None = None,
    google_email: str | None = None,
) -> OtpChallengeResponse:
    try:
        issue = issue_challenge(
            db,
            user,
            google_subject=google_subject,
            google_email=google_email,
        )
        deliver_challenge(user.email, issue)
    except OtpConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication verification is temporarily unavailable",
        ) from None
    except OtpRateLimited as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another verification code",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
    except OtpDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification email could not be sent",
        ) from None
    return _challenge_response(issue)


@router.post(
    "/register",
    response_model=OtpChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register(
    payload: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> OtpChallengeResponse:
    try:
        user = register_user(db, str(payload.email), payload.password)
    except DuplicateEmailError:
        return OtpChallengeResponse(
            challenge_id=uuid4(),
            expires_in_seconds=300,
            resend_after_seconds=60,
            message=OTP_REQUIRED_MESSAGE,
        )
    return _issue_for_user(db, user)


@router.post(
    "/login",
    response_model=OtpChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> OtpChallengeResponse:
    try:
        user = authenticate_user(db, str(payload.email), payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except DisabledUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is disabled",
        ) from None
    return _issue_for_user(db, user)


@router.post(
    "/google",
    response_model=OtpChallengeResponse | GoogleLinkConfirmationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def google_login(
    payload: GoogleLoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> OtpChallengeResponse | GoogleLinkConfirmationResponse:
    try:
        subject, email = google_auth.verify_google_credential(payload.credential)
        result = google_auth.resolve_google_user(
            db,
            subject,
            email,
            confirm_account_link=payload.confirm_account_link,
        )
    except google_auth.GoogleConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is temporarily unavailable",
        ) from None
    except google_auth.InvalidGoogleCredential:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google credential could not be verified",
        ) from None

    if result.link_confirmation_required:
        return GoogleLinkConfirmationResponse(
            message="Confirm linking this Google account, then verify the emailed code.",
        )
    if result.user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google credential could not be verified",
        )
    return _issue_for_user(
        db,
        result.user,
        google_subject=result.subject,
        google_email=result.email,
    )


@router.post(
    "/otp/verify",
    response_model=TokenResponse,
)
def verify_otp(
    payload: OtpVerifyRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        user = verify_challenge(db, payload.challenge_id, payload.code)
    except OtpConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication verification is temporarily unavailable",
        ) from None
    except InvalidOtpError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code is invalid or expired",
        ) from None
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        expires_in=settings.jwt_access_token_minutes * 60,
    )


@router.post(
    "/otp/resend",
    response_model=OtpResendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_otp(
    payload: OtpResendRequest,
    db: Annotated[Session, Depends(get_db)],
) -> OtpResendResponse:
    try:
        issue = resend_challenge(db, payload.challenge_id)
        if issue.code is not None:
            challenge = db.get(EmailOtpChallenge, issue.challenge_id)
            user = db.get(User, challenge.user_id) if challenge is not None else None
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication verification is temporarily unavailable",
                )
            deliver_challenge(user.email, issue)
    except OtpConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication verification is temporarily unavailable",
        ) from None
    except OtpRateLimited as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another verification code",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from None
    except OtpDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification email could not be sent",
        ) from None
    return OtpResendResponse(
        challenge_id=payload.challenge_id,
        retry_after_seconds=issue.resend_after_seconds,
        message="If this sign-in can be completed, a verification code has been sent to your email.",
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    return current_user
