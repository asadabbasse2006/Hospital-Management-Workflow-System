from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Role, User
from app.modules.auth.dependencies import ALL_ROLES
from app.modules.auth.security import hash_password
from app.modules.users import repository
from app.modules.users.schemas import (
    UserCreate,
    UserPublic,
    UserUpdate,
)


def _to_public(user: User, role_name: str) -> UserPublic:
    """Convert a database user to a safe API response."""

    return UserPublic(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        role_id=user.role_id,
        role=role_name,
        department_id=user.department_id,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _validate_role(db: Session, role_id: int) -> Role:
    role = repository.get_role(db, role_id)

    if role is None or role.name not in ALL_ROLES:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail="The selected role is invalid.",
        )

    return role


def _validate_department(
    db: Session,
    department_id: int | None,
) -> None:
    if department_id is None:
        return

    department = repository.get_department(db, department_id)

    if department is None or not department.is_active:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=422,
            detail="The selected department is invalid or inactive.",
        )


def list_staff(
    db: Session,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[UserPublic]:
    rows = repository.list_users(
        db,
        search=search,
        offset=offset,
        limit=limit,
    )
    return [_to_public(user, role_name) for user, role_name in rows]


def get_staff(db: Session, user_id: int) -> UserPublic:
    from fastapi import HTTPException

    row = repository.get_user_with_role(db, user_id)

    if row is None:
        raise HTTPException(status_code=404, detail="User not found.")

    user, role_name = row
    return _to_public(user, role_name)


def create_staff(db: Session, data: UserCreate) -> UserPublic:
    from fastapi import HTTPException

    username = data.username

    if repository.username_exists(db, username):
        raise HTTPException(
            status_code=409,
            detail="That username is already in use.",
        )

    role = _validate_role(db, data.role_id)
    _validate_department(db, data.department_id)

    user = User(
        full_name=data.full_name,
        username=username,
        password_hash=hash_password(
            data.password.get_secret_value()
        ),
        role_id=role.id,
        department_id=data.department_id,
        is_active=True,
    )

    try:
        db.add(user)
        db.flush()
        result = _to_public(user, role.name)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The user could not be created because of a data conflict.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create the user.",
        ) from None


def update_staff(
    db: Session,
    user_id: int,
    data: UserUpdate,
    *,
    actor_id: int,
) -> UserPublic:
    from fastapi import HTTPException

    user = repository.get_user(db, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="No update fields were provided.",
        )

    if "username" in changes:
        username = changes["username"]

        if username is None:
            raise HTTPException(
                status_code=422,
                detail="Username cannot be null.",
            )

        if repository.username_exists(
            db,
            username,
            exclude_user_id=user_id,
        ):
            raise HTTPException(
                status_code=409,
                detail="That username is already in use.",
            )

    if "full_name" in changes and changes["full_name"] is None:
        raise HTTPException(
            status_code=422,
            detail="Full name cannot be null.",
        )

    if "role_id" in changes:
        role_id = changes["role_id"]

        if role_id is None:
            raise HTTPException(
                status_code=422,
                detail="Role cannot be null.",
            )

        new_role = _validate_role(db, role_id)

        # Prevent an administrator from removing their own Admin role.
        if user.id == actor_id and new_role.name != "Admin":
            if user.role_id == new_role.id:
                pass
            else:
                raise HTTPException(
                    status_code=409,
                    detail="You cannot remove your own Admin role.",
                )

        if user.role_id != new_role.id:
            current_role = db.get(Role, user.role_id)

            if current_role and current_role.name == "Admin":
                if new_role.name != "Admin":
                    _ensure_another_active_admin(db, user.id)

    if "department_id" in changes:
        _validate_department(db, changes["department_id"])

    try:
        for field, value in changes.items():
            setattr(user, field, value)

        db.flush()

        row = repository.get_user_with_role(db, user.id)
        if row is None:
            raise HTTPException(
                status_code=500,
                detail="Unable to retrieve the updated user.",
            )

        updated_user, role_name = row
        result = _to_public(updated_user, role_name)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The update conflicts with existing data.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to update the user.",
        ) from None



def _ensure_another_active_admin(
    db: Session,
    excluded_user_id: int,
) -> None:
    from fastapi import HTTPException

    admin_role = db.execute(
        select(Role).where(Role.name == "Admin")
    ).scalar_one_or_none()

    if admin_role is None:
        return

    another_admin = db.execute(
        select(User.id)
        .where(
            User.role_id == admin_role.id,
            User.is_active.is_(True),
            User.id != excluded_user_id,
        )
        .limit(1)
    ).first()

    if another_admin is None:
        raise HTTPException(
            status_code=409,
            detail="The last active administrator cannot be demoted or deactivated.",
        )



def update_staff_status(
    db: Session,
    user_id: int,
    is_active: bool,
    *,
    actor_id: int,
) -> UserPublic:
    from fastapi import HTTPException

    user = repository.get_user(db, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.id == actor_id and not is_active:
        raise HTTPException(
            status_code=409,
            detail="You cannot deactivate your own account.",
        )

    role = db.get(Role, user.role_id)

    if role and role.name == "Admin" and user.is_active and not is_active:
        _ensure_another_active_admin(db, user.id)

    try:
        user.is_active = is_active

        if not is_active:
            repository.revoke_user_sessions(db, user.id)

        row = repository.get_user_with_role(db, user.id)
        if row is None:
            raise HTTPException(
                status_code=500,
                detail="Unable to retrieve the updated user.",
            )

        updated_user, role_name = row
        result = _to_public(updated_user, role_name)
        db.commit()
        return result
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to update the user's status.",
        ) from None
