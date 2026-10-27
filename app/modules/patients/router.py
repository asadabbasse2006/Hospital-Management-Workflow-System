from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import (
    get_current_user,
    require_csrf,
    require_roles,
)
from app.modules.auth.schemas import UserPublic
from app.modules.patients.schemas import (
    CreateVisitRequest,
    PatientCreate,
    PatientRead,
    PatientSearchRead,
    PatientUpdateRequest,
    PatientVisitResponse,
    RegisterPatientWithVisit,
    VisitQueueRead,
    VisitRead,
    VisitStatusTransitionRequest,
)
from app.modules.patients.service import (
    create_visit_for_existing_patient,
    get_patient,
    get_visit_queue,
    register_patient,
    register_patient_with_first_visit,
    search_patients,
    transition_visit,
    update_patient,
)

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "",
    response_model=PatientRead,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Receptionist", "Admin")),
    ],
)
def create_patient(
    data: PatientCreate,
    db: Session = Depends(get_db),
):
    return register_patient(db, data)


@router.post(
    "/register-with-visit",
    response_model=PatientVisitResponse,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Receptionist", "Admin")),
    ],
)
def register_patient_and_visit(
    data: RegisterPatientWithVisit,
    db: Session = Depends(get_db),
):
    return register_patient_with_first_visit(db, data)


@router.get(
    "/search",
    response_model=list[PatientSearchRead],
    dependencies=[
        Depends(require_roles("Admin", "Receptionist", "Doctor")),
    ],
)
def search_patient_records(
    query: str = Query(min_length=1, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    return search_patients(
        db=db,
        query=query,
        offset=offset,
        limit=limit,
        doctor_user_id=(
            current_user.id
            if current_user.role == "Doctor"
            else None
        ),
    )


@router.get(
    "/visits/queue",
    response_model=list[VisitQueueRead],
)
def visit_queue(
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    return get_visit_queue(
        db=db,
        role_name=current_user.role,
        user_id=current_user.id,
    )


@router.get(
    "/{patient_business_id}",
    response_model=PatientRead,
    dependencies=[
        Depends(require_roles("Admin", "Receptionist", "Doctor")),
    ],
)
def get_patient_record(
    patient_business_id: str = Path(min_length=1, max_length=20),
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    return get_patient(
        db=db,
        patient_business_id=patient_business_id,
        doctor_user_id=(
            current_user.id
            if current_user.role == "Doctor"
            else None
        ),
    )


@router.post(
    "/{patient_business_id}/visits",
    response_model=PatientVisitResponse,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Receptionist", "Admin")),
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
    dependencies=[
        Depends(require_csrf),
        Depends(require_roles("Admin", "Receptionist", "Doctor")),
    ],
)
def update_patient_record(
    patient_business_id: str = Path(min_length=1, max_length=20),
    data: PatientUpdateRequest,
    db: Session = Depends(get_db),
    current_user: UserPublic = Depends(get_current_user),
):
    return update_patient(
        db=db,
        patient_business_id=patient_business_id,
        data=data,
        can_update_phone=(current_user.role in ("Receptionist", "Admin")),
        doctor_user_id=(
            current_user.id
            if current_user.role == "Doctor"
            else None
        ),
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
    current_user: UserPublic = Depends(get_current_user),
):
    return transition_visit(
        db=db,
        visit_business_id=visit_business_id,
        target_status=data.status,
        role_name=current_user.role,
        actor_user_id=current_user.id,
        reason=data.reason,
    )
