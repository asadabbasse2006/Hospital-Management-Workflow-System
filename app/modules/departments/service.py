
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Department
from app.modules.departments import repository
from app.modules.departments.schemas import (
    DepartmentCreate,
    DepartmentPublic,
    DepartmentUpdate,
)


def _to_public(department: Department) -> DepartmentPublic:
    """Convert a department model to a safe API response."""
    return DepartmentPublic(
        id=department.id,
        name=department.name,
        is_active=department.is_active,
    )


def list_departments(
    db: Session,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[DepartmentPublic]:
    departments = repository.list_departments(
        db,
        search=search,
        offset=offset,
        limit=limit,
    )
    return [_to_public(department) for department in departments]


def get_department(
    db: Session,
    department_id: int,
) -> DepartmentPublic:
    department = repository.get_department(db, department_id)

    if department is None:
        raise HTTPException(
            status_code=404,
            detail="Department not found.",
        )

    return _to_public(department)


def create_department(
    db: Session,
    data: DepartmentCreate,
) -> DepartmentPublic:
    if repository.get_department_by_name(db, data.name) is not None:
        raise HTTPException(
            status_code=409,
            detail="A department with that name already exists.",
        )

    department = Department(
        name=data.name,
        is_active=True,
    )

    try:
        db.add(department)
        db.flush()
        result = _to_public(department)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A department with that name already exists.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create the department.",
        ) from None


def update_department(
    db: Session,
    department_id: int,
    data: DepartmentUpdate,
) -> DepartmentPublic:
    department = repository.get_department(db, department_id)

    if department is None:
        raise HTTPException(
            status_code=404,
            detail="Department not found.",
        )

    duplicate = repository.get_department_by_name(
        db,
        data.name,
        exclude_department_id=department_id,
    )

    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="A department with that name already exists.",
        )

    try:
        department.name = data.name
        db.flush()
        result = _to_public(department)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A department with that name already exists.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to update the department.",
        ) from None


def update_department_status(
    db: Session,
    department_id: int,
    is_active: bool,
) -> DepartmentPublic:
    department = repository.get_department(db, department_id)

    if department is None:
        raise HTTPException(
            status_code=404,
            detail="Department not found.",
        )

    try:
        department.is_active = is_active
        db.flush()
        result = _to_public(department)
        db.commit()
        return result
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to update the department status.",
        ) from None
