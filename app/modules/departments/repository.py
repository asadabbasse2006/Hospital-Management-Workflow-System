
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Department


def list_departments(
    db: Session,
    *,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[Department]:
    statement = select(Department)

    if search:
        statement = statement.where(
            Department.name.ilike(f"%{search.strip()}%")
        )

    statement = (
        statement
        .order_by(Department.id)
        .offset(offset)
        .limit(limit)
    )

    return list(db.execute(statement).scalars().all())


def get_department(
    db: Session,
    department_id: int,
) -> Department | None:
    return db.get(Department, department_id)


def get_department_by_name(
    db: Session,
    name: str,
    *,
    exclude_department_id: int | None = None,
) -> Department | None:
    statement = select(Department).where(
        Department.name.ilike(name)
    )

    if exclude_department_id is not None:
        statement = statement.where(
            Department.id != exclude_department_id
        )

    return db.execute(statement).scalar_one_or_none()
