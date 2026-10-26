from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select, update, case
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
    VisitStatusHistory
)

from app.modules.patients.schemas import (
    CreateVisitRequest,
    PatientCreate,
    PatientRead,
    PatientVisitResponse,
    RegisterPatientWithVisit,
    VisitRead,
    PatientUpdateRequest,
    VisitQueueRead,
    VisitStatusTransitionRequest
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
    """Create a patient and first visit in one transaction."""
    try:
        _require_active_doctor(db, data.doctor_id)
        _ensure_patient_does_not_exist(
            db,
            data.cnic,
            data.phone,
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

        db.commit()
        return result

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "A unique identifier or database constraint conflicted. "
                "Search for the patient and retry with valid details."
            ),
        ) from exc

    except Exception:
        db.rollback()
        raise



def create_visit_for_existing_patient(
    db: Session,
    patient_business_id: str,
    data: CreateVisitRequest,
) -> PatientVisitResponse:
    """Create another visit without creating a duplicate patient."""
    try:
        patient = db.scalar(
            select(Patient).where(
                Patient.patient_id == patient_business_id.strip().upper()
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

        db.commit()
        return result

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A database constraint conflicted. Please retry.",
        ) from exc

    except Exception:
        db.rollback()
        raise

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


def update_patient(
    db: Session,
    patient_business_id: str,
    data: PatientUpdateRequest,
    *,
    can_update_phone: bool,
) -> PatientRead:
    """Update permitted patient fields and enforce field-level access."""
    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update.",
        )

    if "phone" in changes and not can_update_phone:
        raise HTTPException(
            status_code=403,
            detail="Only Receptionists can update a patient's phone number.",
        )

    patient = db.scalar(
        select(Patient).where(
            Patient.patient_id == patient_business_id.strip().upper()
        )
    )

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found.",
        )

    try:
        for field, value in changes.items():
            setattr(patient, field, value)

        # Preserve the database rule that a patient must have
        # at least a CNIC or phone number.
        if not patient.cnic and not patient.phone:
            raise HTTPException(
                status_code=422,
                detail="A patient must have a CNIC or phone number.",
            )

        db.flush()
        result = PatientRead.model_validate(patient)
        db.commit()
        return result

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "The updated details conflict with an existing record. "
                "Check the phone number and retry."
            ),
        ) from exc

    except Exception:
        db.rollback()
        raise


from sqlalchemy import select

from app.db.models import Patient, Visit

from app.modules.patients.workflow import can_transition


def transition_visit(
    db: Session,
    visit_business_id: str,
    target_status: str,
    role_name: str,
    actor_user_id: int,
    reason: str | None = None,
) -> Visit:
    """Apply a permitted visit status transition."""
    try:
        visit = db.scalar(
            select(Visit)
            .where(Visit.visit_id == visit_business_id.strip().upper())
            .with_for_update()
        )

        if visit is None:
            raise HTTPException(
                status_code=404,
                detail="Visit not found.",
            )

        if not can_transition(
            visit.status,
            role_name,
            target_status,
        ):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Role '{role_name}' cannot change a visit "
                    f"from '{visit.status}' to '{target_status}'."
                ),
            )
        old_status = visit.status

        visit.status = target_status

        if target_status == "Completed":
            visit.closed_at = datetime.now(ZoneInfo("Asia/Karachi"))

        db.add(
            VisitStatusHistory(
                visit_pk=visit.id,
                changed_by_user_id=actor_user_id,
                from_status=old_status,
                to_status=target_status,
                reason=reason,
            )
        )

        db.flush()
        db.commit()
        db.refresh(visit)
        return visit

    except Exception:
        db.rollback()
        raise


def get_visit_queue(
    db: Session,
    role_name: str,
    user_id: int,
) -> list[dict]:
    """Return the open queue relevant to the caller's department."""
    role_statuses = {
        "Receptionist": ["Receptionist", "Visits"],
        "Doctor": ["With Doctor"],
        "Lab Assistant": ["Lab Tests"],
        "Pathologist": ["Lab Tests"],
        "Pharmacy Assistant": ["Pharmacy"],
        "Printing Assistant": ["Printing"],
    }

    if role_name == "Admin":
        statuses = [
            "Receptionist",
            "Visits",
            "With Doctor",
            "Lab Tests",
            "Pharmacy",
            "Printing",
        ]
    else:
        statuses = role_statuses.get(role_name, [])

    if not statuses:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to a visit queue.",
        )

    statement = (
        select(Visit, Patient)
        .join(Patient, Patient.id == Visit.patient_id)
        .where(Visit.status.in_(statuses))
        .order_by(
            case(
                (Visit.priority == "Emergency", 0),
                else_=1,
            ),
            Visit.created_at.asc(),
        )
    )

    # Doctors should see only their own assigned visits.
    if role_name == "Doctor":
        statement = statement.where(Visit.doctor_id == user_id)

    rows = db.execute(statement).all()

    return [
        {
            "id": visit.id,
            "visit_id": visit.visit_id,
            "patient_business_id": patient.patient_id,
            "patient_name": patient.patient_name,
            "doctor_id": visit.doctor_id,
            "status": visit.status,
            "priority": visit.priority,
            "created_at": visit.created_at,
        }
        for visit, patient in rows
    ]
