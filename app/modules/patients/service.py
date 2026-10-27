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
    PatientSearchRead,
    PatientVisitResponse,
    RegisterPatientWithVisit,
    VisitRead,
    PatientUpdateRequest,
    VisitQueueRead,
    VisitStatusTransitionRequest
)

from app.modules.patients.schemas import normalize_cnic, normalize_phone
from app.modules.patients.workflow import can_transition

PATIENT_ID_RETRY_LIMIT = 5
PATIENT_ID_UNIQUE_CONSTRAINT = "uq_patients_patient_id"
PATIENT_CONTACT_UNIQUE_CONSTRAINTS = {
    "uq_patients_cnic",
    "uq_patients_phone",
}


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    return getattr(diag, "constraint_name", None)


def _conflict_http_exception(exc: IntegrityError) -> HTTPException:
    constraint = _constraint_name(exc)
    if constraint in PATIENT_CONTACT_UNIQUE_CONSTRAINTS:
        return HTTPException(
            status_code=409,
            detail=(
                "A patient with this CNIC or phone number already exists. "
                "Search for the existing patient before registering another."
            ),
        )
    return HTTPException(
        status_code=409,
        detail=(
            "A unique identifier or database constraint conflicted. "
            "Search for the patient and retry with valid details."
        ),
    )


def _escape_like_term(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


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


def _create_patient_record(db: Session, data: PatientCreate) -> Patient:
    """Insert a patient with a generated identifier. Does not commit."""
    _ensure_patient_does_not_exist(db, data.cnic, data.phone)

    last_conflict: IntegrityError | None = None

    for _ in range(PATIENT_ID_RETRY_LIMIT):
        patient_id = _next_patient_id(db)

        try:
            with db.begin_nested():
                patient = Patient(
                    patient_id=patient_id,
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
                return patient
        except IntegrityError as exc:
            last_conflict = exc
            if _constraint_name(exc) == PATIENT_ID_UNIQUE_CONSTRAINT:
                continue
            raise _conflict_http_exception(exc) from exc

    if last_conflict is not None:
        raise _conflict_http_exception(last_conflict) from last_conflict

    raise HTTPException(
        status_code=409,
        detail=(
            "A unique identifier or database constraint conflicted. "
            "Search for the patient and retry with valid details."
        ),
    )


def register_patient(
    db: Session,
    data: PatientCreate,
) -> PatientRead:
    """Register a patient and persist a unique business identifier."""
    try:
        patient = _create_patient_record(db, data)
        result = PatientRead.model_validate(patient)
        db.commit()
        return result

    except IntegrityError as exc:
        db.rollback()
        raise _conflict_http_exception(exc) from exc

    except Exception:
        db.rollback()
        raise


def register_patient_with_first_visit(
    db: Session,
    data: RegisterPatientWithVisit,
) -> PatientVisitResponse:
    """Create a patient and first visit in one transaction."""
    try:
        _require_active_doctor(db, data.doctor_id)
        patient = _create_patient_record(db, data)

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
        raise _conflict_http_exception(exc) from exc

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


def _patient_visible_to_doctor(doctor_user_id: int):
    return (
        select(Visit.id)
        .where(
            Visit.patient_id == Patient.id,
            Visit.doctor_id == doctor_user_id,
        )
        .exists()
    )


def get_patient(
    db: Session,
    patient_business_id: str,
    *,
    doctor_user_id: int | None = None,
) -> PatientRead:
    """Return one patient by generated identifier, or 404."""
    identifier = patient_business_id.strip().upper()

    if not identifier:
        raise HTTPException(
            status_code=422,
            detail="Enter a valid Patient ID.",
        )

    statement = select(Patient).where(Patient.patient_id == identifier)

    if doctor_user_id is not None:
        statement = statement.where(_patient_visible_to_doctor(doctor_user_id))

    patient = db.scalar(statement)

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found.",
        )

    return PatientRead.model_validate(patient)


def search_patients(
    db: Session,
    query: str,
    *,
    offset: int = 0,
    limit: int = 50,
    doctor_user_id: int | None = None,
) -> list[PatientSearchRead]:
    """Search patients at the database, with stable ordering and pagination."""
    query = query.strip()

    if not query:
        raise HTTPException(
            status_code=422,
            detail="Enter a Patient ID, name, CNIC, or phone number.",
        )

    like_term = f"%{_escape_like_term(query)}%"
    conditions = [
        Patient.patient_id == query.upper(),
        Patient.patient_name.ilike(like_term, escape="\\"),
    ]
    digits = "".join(character for character in query if character.isdigit())

    if len(digits) == 13:
        try:
            cnic = normalize_cnic(query)
            if cnic:
                conditions.append(Patient.cnic == cnic)
        except ValueError:
            pass

    if 7 <= len(digits) <= 15:
        try:
            phone = normalize_phone(query)
            if phone:
                conditions.append(Patient.phone == phone)
        except ValueError:
            pass

    statement = select(
        Patient.patient_id,
        Patient.patient_name,
        Patient.gender,
    ).where(or_(*conditions))

    if doctor_user_id is not None:
        statement = statement.where(_patient_visible_to_doctor(doctor_user_id))

    statement = (
        statement.order_by(Patient.created_at.desc(), Patient.id.asc())
        .offset(offset)
        .limit(limit)
    )

    patients = db.execute(statement).all()
    return [
        PatientSearchRead.model_validate(patient._mapping)
        for patient in patients
    ]


def update_patient(
    db: Session,
    patient_business_id: str,
    data: PatientUpdateRequest,
    *,
    can_update_phone: bool,
    doctor_user_id: int | None = None,
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
            detail=(
                "Only Receptionists and Admins can update a patient's "
                "phone number."
            ),
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

    if doctor_user_id is not None:
        has_assigned_visit = db.scalar(
            select(Visit.id)
            .where(
                Visit.patient_id == patient.id,
                Visit.doctor_id == doctor_user_id,
            )
            .limit(1)
        )
        if has_assigned_visit is None:
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

        if visit is None or (role_name == "Doctor" and visit.doctor_id != actor_user_id):
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
