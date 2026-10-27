
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_csrf, require_roles
from app.modules.auth.schemas import UserPublic as AuthUserPublic
from app.modules.users import service
from app.modules.users.schemas import (
    UserCreate,
    UserPublic,
    UserStatusUpdate,
    UserUpdate,
)


router = APIRouter(prefix="/users", tags=["User Management"])

AdminUser = Annotated[
    AuthUserPublic,
    Depends(require_roles("Admin")),
]

CSRFProtection = Annotated[
    None,
    Depends(require_csrf),
]


@router.get("", response_model=list[UserPublic])
def list_users(
    _admin: AdminUser,
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return service.list_staff(
        db,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.post(
    "",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    data: UserCreate,
    _csrf: CSRFProtection,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.create_staff(db, data)


@router.get("/{user_id}", response_model=UserPublic)
def get_user(
    user_id: int,
    _admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.get_staff(db, user_id)


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int,
    data: UserUpdate,
    _csrf: CSRFProtection,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.update_staff(
        db,
        user_id,
        data,
        actor_id=admin.id,
    )


@router.patch("/{user_id}/status", response_model=UserPublic)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    _csrf: CSRFProtection,
    admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.update_staff_status(
        db,
        user_id,
        data.is_active,
        actor_id=admin.id,
    )
