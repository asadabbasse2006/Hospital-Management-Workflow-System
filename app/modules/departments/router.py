
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_csrf, require_roles
from app.modules.auth.schemas import UserPublic as AuthUserPublic
from app.modules.departments import service
from app.modules.departments.schemas import (
    DepartmentCreate,
    DepartmentPublic,
    DepartmentStatusUpdate,
    DepartmentUpdate,
)


router = APIRouter(prefix="/departments", tags=["Department Management"])

AdminUser = Annotated[
    AuthUserPublic,
    Depends(require_roles("Admin")),
]

CSRFProtection = Annotated[
    None,
    Depends(require_csrf),
]


@router.get("", response_model=list[DepartmentPublic])
def list_departments(
    _admin: AdminUser,
    db: Session = Depends(get_db),
    search: str | None = Query(default=None, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    return service.list_departments(
        db,
        search=search,
        offset=offset,
        limit=limit,
    )


@router.post(
    "",
    response_model=DepartmentPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    data: DepartmentCreate,
    _csrf: CSRFProtection,
    _admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.create_department(db, data)


@router.get("/{department_id}", response_model=DepartmentPublic)
def get_department(
    department_id: int,
    _admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.get_department(db, department_id)


@router.patch("/{department_id}", response_model=DepartmentPublic)
def update_department(
    department_id: int,
    data: DepartmentUpdate,
    _csrf: CSRFProtection,
    _admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.update_department(
        db,
        department_id,
        data,
    )


@router.patch(
    "/{department_id}/status",
    response_model=DepartmentPublic,
)
def update_department_status(
    department_id: int,
    data: DepartmentStatusUpdate,
    _csrf: CSRFProtection,
    _admin: AdminUser,
    db: Session = Depends(get_db),
):
    return service.update_department_status(
        db,
        department_id,
        data.is_active,
    )
