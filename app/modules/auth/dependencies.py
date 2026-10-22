from datetime import datetime, timezone
import hmac

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Role, User, UserSession
from app.db.session import get_db
from app.modules.auth.schemas import UserPublic
from app.modules.auth.security import hash_session_token


SESSION_TTL_HOURS = 8
SESSION_TTL_SECONDS = SESSION_TTL_HOURS * 60 * 60

# The __Host- prefix is used only when running behind HTTPS in production.
SESSION_COOKIE_NAME = (
    "__Host-hospital_session"
    if settings.app_env == "production"
    else "hospital_session"
)

COOKIE_SECURE = settings.app_env == "production"

ALL_ROLES = (
    "Admin",
    "Receptionist",
    "Doctor",
    "Lab Assistant",
    "Pathologist",
    "Pharmacy Assistant",
    "Printing Assistant",
)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE_NAME,
    ),
) -> UserPublic:
    """Validate the session cookie and return the authenticated user."""

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    token_digest = hash_session_token(session_token)

    statement = (
        select(UserSession, User, Role.name)
        .join(User, User.id == UserSession.user_id)
        .join(Role, Role.id == User.role_id)
        .where(
            UserSession.token_hash == token_digest,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
    )

    row = db.execute(statement).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=401,
            detail="Session is invalid or expired.",
        )

    session_record, user, role_name = row

    # Used by the CSRF and logout dependencies for this request.
    request.state.auth_session = session_record

    return UserPublic(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=role_name,
        department_id=user.department_id,
    )


def require_roles(*allowed_roles: str):
    """Build a dependency that rejects users without an allowed role."""

    def role_checker(
        current_user: UserPublic = Depends(get_current_user),
    ) -> UserPublic:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )

        return current_user

    return role_checker


def require_csrf(
    request: Request,
    x_csrf_token: str | None = Header(
        default=None,
        alias="X-CSRF-Token",
    ),
    _current_user: UserPublic = Depends(get_current_user),
) -> None:
    """Require the CSRF token associated with the authenticated session."""

    session_record = getattr(request.state, "auth_session", None)

    if (
        session_record is None
        or not x_csrf_token
        or not hmac.compare_digest(
            session_record.csrf_token,
            x_csrf_token,
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Missing or invalid CSRF token.",
        )