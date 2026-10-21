from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.models import Role, User, UserSession
from app.db.session import get_db
from app.modules.auth.dependencies import (
    COOKIE_SECURE,
    SESSION_COOKIE_NAME,
    SESSION_TTL_HOURS,
    SESSION_TTL_SECONDS,
    get_current_user,
    require_csrf,
)
from app.modules.auth.schemas import (
    CSRFResponse,
    LoginRequest,
    LoginResponse,
    UserPublic,
)
from app.modules.auth.security import (
    DUMMY_PASSWORD_HASH,
    hash_session_token,
    verify_password,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    """Verify credentials and establish a server-side session."""

    statement = (
        select(User, Role.name)
        .join(Role, Role.id == User.role_id)
        .where(User.username == data.username)
    )

    row = db.execute(statement).one_or_none()
    password = data.password.get_secret_value()

    if row is None:
        verify_password(password, DUMMY_PASSWORD_HASH)

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    user, role_name = row
    password_valid = verify_password(password, user.password_hash)

    if not password_valid or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password.",
        )

    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=SESSION_TTL_HOURS)

    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(raw_token),
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
    )

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to establish a session.",
        ) from None

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )

    return LoginResponse(
        user=UserPublic(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=role_name,
            department_id=user.department_id,
        ),
        csrf_token=csrf_token,
    )


@router.get("/me", response_model=UserPublic)
def get_me(
    current_user: UserPublic = Depends(get_current_user),
):
    """Return the authenticated user's public profile."""
    return current_user


@router.get("/csrf", response_model=CSRFResponse)
def get_csrf_token(
    request: Request,
    _current_user: UserPublic = Depends(get_current_user),
):
    """Return the CSRF token associated with the current session."""
    return CSRFResponse(
        csrf_token=request.state.auth_session.csrf_token
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
    _current_user: UserPublic = Depends(get_current_user),
):
    """Revoke the current session and clear its cookie."""

    session_record = request.state.auth_session
    session_record.revoked_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to end the session.",
        ) from None

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )

    return {"status": "logged_out"}