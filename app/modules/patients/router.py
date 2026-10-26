from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import get_db
from app.modules.patients.schemas import (
    CreateVisitRequest,
    PatientRead,
    PatientVisitResponse,
    RegisterPatientWithVisit,
)

from app.db.models import Role, User
from app.modules.patients.schemas import PatientUpdateRequest
from app.modules.patients.service import update_patient

from app.db.models import Role, User
from app.modules.patients.schemas import (
    VisitQueueRead,
    VisitStatusTransitionRequest,
    VisitRead,
)

from app.modules.patients.service import (
    get_visit_queue,
    transition_visit,
)

from app.modules.patients.service import (
    create_visit_for_existing_patient,
    register_patient_with_first_visit,
    search_patients,
)

from fastapi import HTTPException

from app.modules.auth.dependencies import (
    get_current_user,
    require_csrf,
    require_roles,
)

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/register-with-visit",
    response_model=PatientVisitResponse,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Receptionist")),
    ],
)
def register_patient(
    data: RegisterPatientWithVisit,
    db: Session = Depends(get_db),
):
    return register_patient_with_first_visit(db, data)



@router.get(
    "/search",
    response_model=list[PatientRead],
    dependencies=[
        Depends(
            require_roles(
                "Admin",
                "Receptionist",
                "Doctor",
            )
        ),
    ],
)
def search_patient_records(
    query: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    return search_patients(db, query)



@router.post(
    "/{patient_business_id}/visits",
    response_model=PatientVisitResponse,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Receptionist")),
    ],
)
def create_existing_patient_visit(
    patient_business_id: str,
    data: CreateVisitRequest,
    db: Session = Depends(get_db),
):
    return create_visit_for_existing_patient(
        db, patient_business_id, data
    )


@router.patch(
    "/{patient_business_id}",
    response_model=PatientRead,
    dependencies=[Depends(require_csrf)],
)
def update_patient_record(
    patient_business_id: str,
    data: PatientUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = db.scalar(
        select(Role.name)
        .join(User, User.role_id == Role.id)
        .where(User.id == current_user.id)
    )

    if role_name not in {"Receptionist", "Doctor"}:
        raise HTTPException(
            status_code=403,
            detail="You are not permitted to update patient records.",
        )

    return update_patient(
        db=db,
        patient_business_id=patient_business_id,
        data=data,
        can_update_phone=(role_name == "Receptionist"),
    )


def _get_current_role(db: Session, user_id: int) -> str:
    role_name = db.scalar(
        select(Role.name)
        .join(User, User.role_id == Role.id)
        .where(User.id == user_id)
    )

    if not role_name:
        raise HTTPException(
            status_code=403,
            detail="No valid role is assigned to this user.",
        )

    return role_name


@router.get(
    "/visits/queue",
    response_model=list[VisitQueueRead],
)
def visit_queue(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = _get_current_role(db, current_user.id)

    return get_visit_queue(
        db=db,
        role_name=role_name,
        user_id=current_user.id,
    )


@router.patch(
    "/visits/{visit_business_id}/status",
    response_model=VisitRead,
    dependencies=[Depends(require_csrf)],
)
def change_visit_status(
    visit_business_id: str,
    data: VisitStatusTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = _get_current_role(db, current_user.id)

    visit = transition_visit(
        db=db,
        visit_business_id=visit_business_id,
        target_status=data.status,
        role_name=role_name,
        actor_user_id=current_user.id,
        reason=data.reason,
    )

    return visit
