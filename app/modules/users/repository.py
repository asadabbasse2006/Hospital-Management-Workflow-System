
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Department, Role, User, UserSession


def list_users(
    db: Session,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[tuple[User, str]]:
    """Return users with their role names."""

    statement = (
        select(User, Role.name)
        .join(Role, Role.id == User.role_id)
        .order_by(User.id)
        .offset(offset)
        .limit(limit)
    )

    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            User.username.ilike(term)
            | User.full_name.ilike(term)
        )

    return list(db.execute(statement).all())


def get_user(db: Session, user_id: int) -> User | None:
    """Return a user by primary key."""

    return db.get(User, user_id)


def get_user_with_role(
    db: Session,
    user_id: int,
) -> tuple[User, str] | None:
    """Return a user and role name, or None if not found."""

    statement = (
        select(User, Role.name)
        .join(Role, Role.id == User.role_id)
        .where(User.id == user_id)
    )

    return db.execute(statement).one_or_none()


def get_role(db: Session, role_id: int) -> Role | None:
    return db.get(Role, role_id)


def get_department(
    db: Session,
    department_id: int,
) -> Department | None:
    return db.get(Department, department_id)


def username_exists(
    db: Session,
    username: str,
    *,
    exclude_user_id: int | None = None,
) -> bool:
    statement = select(User.id).where(User.username == username)

    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)

    return db.execute(statement).first() is not None


def revoke_user_sessions(db: Session, user_id: int) -> None:
    """Revoke every active session belonging to a user."""

    from datetime import datetime, timezone

    statement = select(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    )

    now = datetime.now(timezone.utc)

    for session in db.scalars(statement):
        session.revoked_at = now
