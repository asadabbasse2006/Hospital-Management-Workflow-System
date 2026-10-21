from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    DoctorProfile,
    IdSequence,
    Patient,
    Role,
    User,
    Visit,
)
from app.modules.patients.schemas import (
    CreateVisitRequest,
    PatientCreate,
    PatientRead,
    PatientVisitResponse,
    RegisterPatientWithVisit,
    VisitRead,
)
from app.modules.patients.schemas import normalize_cnic, normalize_phone


def _next_sequence(db: Session, sequence_name: str) -> int:
    """Atomically increment a named business-ID sequence."""
    insert_statement = (
        pg_insert(IdSequence)
        .values(name=sequence_name, value=0)
        .on_conflict_do_nothing(index_elements=[IdSequence.name])
    )
    db.execute(insert_statement)

    value = db.execute(
        update(IdSequence)
        .where(IdSequence.name == sequence_name)
        .values(value=IdSequence.value + 1)
        .returning(IdSequence.value)
    ).scalar_one()

    return value


def _next_patient_id(db: Session) -> str:
    number = _next_sequence(db, "patient")
    return f"PAT-{number:06d}"


def _next_visit_id(db: Session) -> str:
    year = datetime.now(ZoneInfo("Asia/Karachi")).year
    number = _next_sequence(db, f"visit_{year}")
    return f"VIS-{year}-{number:05d}"


def _require_active_doctor(db: Session, doctor_id: int) -> None:
    """Require an active user with the Doctor role and a doctor profile."""
    statement = (
        select(User.id)
        .join(Role, Role.id == User.role_id)
        .join(DoctorProfile, DoctorProfile.user_id == User.id)
        .where(
            User.id == doctor_id,
            Role.name == "Doctor",
            User.is_active.is_(True),
        )
    )

    if db.scalar(statement) is None:
        raise HTTPException(
            status_code=422,
            detail="Select an active doctor with a configured doctor profile.",
        )


def _ensure_patient_does_not_exist(
    db: Session,
    cnic: str | None,
    phone: str | None,
) -> None:
    conditions = []

    if cnic:
        conditions.append(Patient.cnic == cnic)

    if phone:
        conditions.append(Patient.phone == phone)

    if conditions and db.scalar(
        select(Patient.id).where(or_(*conditions)).limit(1)
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "A patient with this CNIC or phone number already exists. "
                "Search for the existing patient before registering another."
            ),
        )


def _new_visit(
    db: Session,
    patient: Patient,
    doctor_id: int,
    priority: str,
) -> Visit:
    _require_active_doctor(db, doctor_id)

    visit = Visit(
        visit_id=_next_visit_id(db),
        patient_id=patient.id,
        doctor_id=doctor_id,
        parent_visit_id=None,
        status="Receptionist",
        priority=priority,
    )
    db.add(visit)
    db.flush()

    return visit


def register_patient_with_first_visit(
    db: Session,
    data: RegisterPatientWithVisit,
) -> PatientVisitResponse:
    """Create a patient and first visit atomically."""
    try:
        with db.begin():
            _require_active_doctor(db, data.doctor_id)
            _ensure_patient_does_not_exist(
                db, data.cnic, data.phone
            )

            patient = Patient(
                patient_id=_next_patient_id(db),
                patient_name=data.patient_name,
                cnic=data.cnic,
                father_or_husband_name=data.father_or_husband_name,
                location=data.location,
                phone=data.phone,
                date_of_birth=data.date_of_birth,
                gender=data.gender,
                address=data.address,
            )
            db.add(patient)
            db.flush()

            visit = Visit(
                visit_id=_next_visit_id(db),
                patient_id=patient.id,
                doctor_id=data.doctor_id,
                parent_visit_id=None,
                status="Receptionist",
                priority=data.priority,
            )
            db.add(visit)
            db.flush()

            result = PatientVisitResponse(
                patient=PatientRead.model_validate(patient),
                visit=VisitRead.model_validate(visit),
            )

        # The transaction commits successfully before returning.
        return result

    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "A unique identifier or database constraint conflicted. "
                "Search for the patient and retry with valid details."
            ),
        ) from exc


def create_visit_for_existing_patient(
    db: Session,
    patient_business_id: str,
    data: CreateVisitRequest,
) -> PatientVisitResponse:
    """Create another visit without creating a duplicate patient."""
    try:
        with db.begin():
            patient = db.scalar(
                select(Patient).where(
                    Patient.patient_id == patient_business_id.upper()
                )
            )

            if patient is None:
                raise HTTPException(
                    status_code=404,
                    detail="Patient not found.",
                )

            visit = _new_visit(
                db=db,
                patient=patient,
                doctor_id=data.doctor_id,
                priority=data.priority,
            )

            result = PatientVisitResponse(
                patient=PatientRead.model_validate(patient),
                visit=VisitRead.model_validate(visit),
            )

        return result

    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="A database constraint conflicted. Please retry.",
        ) from exc


def search_patients(
    db: Session,
    query: str,
) -> list[PatientRead]:
    """Exact search using patient ID, CNIC, or phone."""
    query = query.strip()

    if not query:
        raise HTTPException(
            status_code=422,
            detail="Enter a Patient ID, CNIC, or phone number.",
        )

    conditions = [Patient.patient_id == query.upper()]
    digits = "".join(character for character in query if character.isdigit())

    if len(digits) == 13:
        try:
            cnic = normalize_cnic(query)
            if cnic:
                conditions.append(Patient.cnic == cnic)
        except ValueError:
            pass

    if len(digits) >= 7:
        try:
            phone = normalize_phone(query)
            if phone:
                conditions.append(Patient.phone == phone)
        except ValueError:
            pass

    statement = (
        select(Patient)
        .where(or_(*conditions))
        .order_by(Patient.created_at.desc())
        .limit(20)
    )

    patients = db.scalars(statement).all()
    return [PatientRead.model_validate(patient) for patient in patients]