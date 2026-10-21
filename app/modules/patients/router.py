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


def require_development_mode() -> None:
    """Keep unauthenticated patient APIs disabled outside local development."""
    if settings.app_env != "development":
        raise HTTPException(
            status_code=503,
            detail=(
                "Patient APIs are disabled outside development until "
                "authentication and role-based authorization are implemented."
            ),
        )


router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    dependencies=[Depends(require_development_mode)],
)


@router.post(
    "/register-with-visit",
    response_model=PatientVisitResponse,
    status_code=201,
)
def register_patient(
    data: RegisterPatientWithVisit,
    db: Session = Depends(get_db),
):
    return register_patient_with_first_visit(db, data)


@router.get("/search", response_model=list[PatientRead])
def search_patient_records(
    query: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
):
    return search_patients(db, query)


@router.post(
    "/{patient_business_id}/visits",
    response_model=PatientVisitResponse,
    status_code=201,
)
def create_existing_patient_visit(
    patient_business_id: str,
    data: CreateVisitRequest,
    db: Session = Depends(get_db),
):
    return create_visit_for_existing_patient(
        db, patient_business_id, data
    )