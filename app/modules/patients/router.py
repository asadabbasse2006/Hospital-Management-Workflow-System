from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.modules.patients.schemas import (
    CreateVisitRequest,
    PatientRead,
    PatientVisitResponse,
    RegisterPatientWithVisit,
)
from app.modules.patients.service import (
    create_visit_for_existing_patient,
    register_patient_with_first_visit,
    search_patients,
)

from fastapi import HTTPException

from app.modules.auth.dependencies import (
    ALL_ROLES,
    get_current_user,
    require_csrf,
    require_roles,
)

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(get_current_user)],
)

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    # dependencies=[Depends(require_development_mode)],
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
        Depends(require_roles(*ALL_ROLES)),
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