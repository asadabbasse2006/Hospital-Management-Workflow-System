import pytest
from sqlalchemy import select

from app.core.rate_limit import limiter
from app.db.models import DoctorProfile, IdSequence, Patient, Role, User, Visit
from app.modules.auth.security import hash_password
from app.modules.patients import service as patient_service
from app.modules.patients.schemas import PatientCreate, RegisterPatientWithVisit


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def registration_setup(db):
    roles = {}
    for role_name in ["Admin", "Receptionist", "Doctor", "Lab Assistant"]:
        role = Role(name=role_name)
        db.add(role)
        roles[role_name] = role
    db.flush()

    receptionist = User(
        full_name="Registration Receptionist",
        username="reg.recep",
        password_hash=hash_password("RecepPass!123"),
        role_id=roles["Receptionist"].id,
        is_active=True,
    )
    doctor = User(
        full_name="Registration Doctor",
        username="reg.doctor",
        password_hash=hash_password("DoctorPass!123"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    lab_assistant = User(
        full_name="Registration Lab Assistant",
        username="reg.lab",
        password_hash=hash_password("LabPass!12345"),
        role_id=roles["Lab Assistant"].id,
        is_active=True,
    )
    db.add_all([receptionist, doctor, lab_assistant])
    db.flush()
    db.add(DoctorProfile(user_id=doctor.id, consultation_fee=1000))
    db.flush()

    return {
        "receptionist": receptionist,
        "doctor": doctor,
        "lab_assistant": lab_assistant,
    }


def login_helper(client, username, password):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_register_patient_success_generates_and_persists_id(
    client, db, registration_setup
):
    csrf_token = login_helper(client, "reg.recep", "RecepPass!123")

    response = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "  Ali   Khan  ",
            "cnic": "35202-1234567-1",
            "phone": "03001234567",
            "father_or_husband_name": "  Ahmed Khan ",
            "gender": "Male",
            "location": "Lahore",
            "address": "House 1",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["patient_name"] == "Ali Khan"
    assert body["father_or_husband_name"] == "Ahmed Khan"
    assert body["cnic"] == "3520212345671"
    assert body["phone"] == "+923001234567"
    assert body["patient_id"].startswith("PAT-")

    stored = db.scalar(
        select(Patient).where(Patient.patient_id == body["patient_id"])
    )
    assert stored is not None
    assert stored.patient_name == "Ali Khan"
    assert stored.cnic == "3520212345671"


def test_register_patient_requires_name_and_contact(client, registration_setup):
    csrf_token = login_helper(client, "reg.recep", "RecepPass!123")

    missing_name = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={"phone": "03001112233"},
    )
    assert missing_name.status_code == 422

    missing_contact = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={"patient_name": "No Contact"},
    )
    assert missing_contact.status_code == 422

    invalid_cnic = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={"patient_name": "Bad CNIC", "cnic": "12345"},
    )
    assert invalid_cnic.status_code == 422


def test_register_patient_rejects_duplicate_phone_and_cnic(
    client, db, registration_setup
):
    csrf_token = login_helper(client, "reg.recep", "RecepPass!123")

    first = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "First Patient",
            "cnic": "3520211111111",
            "phone": "03001110001",
        },
    )
    assert first.status_code == 201, first.text

    duplicate_phone = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "Second Patient",
            "phone": "03001110001",
        },
    )
    assert duplicate_phone.status_code == 409
    assert "already exists" in duplicate_phone.json()["detail"]

    duplicate_cnic = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "Third Patient",
            "cnic": "35202-1111111-1",
        },
    )
    assert duplicate_cnic.status_code == 409

    count = len(db.scalars(select(Patient)).all())
    assert count == 1


def test_register_patient_retries_duplicate_generated_id(
    client, db, registration_setup
):
    db.add(
        Patient(
            patient_id="PAT-000001",
            patient_name="Existing Sequence Patient",
            phone="+923001119999",
        )
    )
    db.add(IdSequence(name="patient", value=0))
    db.flush()

    csrf_token = login_helper(client, "reg.recep", "RecepPass!123")
    response = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "Retry Patient",
            "phone": "03001118888",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["patient_id"] == "PAT-000002"

    stored = db.scalar(
        select(Patient).where(Patient.patient_id == "PAT-000002")
    )
    assert stored is not None


def test_register_patient_unauthenticated_is_rejected(client):
    response = client.post(
        "/api/v1/patients",
        json={"patient_name": "No Auth", "phone": "03001110002"},
    )
    assert response.status_code == 401


def test_register_patient_forbidden_for_doctor_and_lab(
    client, registration_setup
):
    doctor_csrf = login_helper(client, "reg.doctor", "DoctorPass!123")
    doctor_response = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": doctor_csrf},
        json={"patient_name": "Doctor Register", "phone": "03001110003"},
    )
    assert doctor_response.status_code == 403

    lab_csrf = login_helper(client, "reg.lab", "LabPass!12345")
    lab_response = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": lab_csrf},
        json={"patient_name": "Lab Register", "phone": "03001110004"},
    )
    assert lab_response.status_code == 403


def test_register_patient_requires_csrf(client, registration_setup):
    login_helper(client, "reg.recep", "RecepPass!123")

    missing = client.post(
        "/api/v1/patients",
        json={"patient_name": "No CSRF", "phone": "03001110005"},
    )
    assert missing.status_code == 403
    assert missing.json()["detail"] == "Missing or invalid CSRF token."

    invalid = client.post(
        "/api/v1/patients",
        headers={"X-CSRF-Token": "not-a-valid-token"},
        json={"patient_name": "Bad CSRF", "phone": "03001110006"},
    )
    assert invalid.status_code == 403


def test_register_with_visit_rolls_back_patient_on_failure(
    db, registration_setup, monkeypatch
):
    def fail_visit_id(_db):
        raise RuntimeError("visit identifier failed")

    monkeypatch.setattr(patient_service, "_next_visit_id", fail_visit_id)

    payload = RegisterPatientWithVisit(
        patient_name="Rollback Patient",
        phone="03001110007",
        doctor_id=registration_setup["doctor"].id,
        priority="Normal",
    )

    with pytest.raises(RuntimeError, match="visit identifier failed"):
        patient_service.register_patient_with_first_visit(db, payload)

    leftover = db.scalar(
        select(Patient).where(Patient.patient_name == "Rollback Patient")
    )
    assert leftover is None
    leftover_visits = db.scalars(select(Visit)).all()
    assert leftover_visits == []


def test_register_patient_rolls_back_when_commit_fails(
    db, registration_setup, monkeypatch
):
    def fail_commit():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        patient_service.register_patient(
            db,
            PatientCreate(
                patient_name="Commit Failure Patient",
                phone="03001110008",
            ),
        )

    leftover = db.scalar(
        select(Patient).where(
            Patient.patient_name == "Commit Failure Patient"
        )
    )
    assert leftover is None
