import pytest

from app.db.models import DoctorProfile, Patient, Role, User, Visit, VisitStatusHistory
from app.modules.auth.security import hash_password
from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    """Reset in-memory rate-limit state between authentication tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()



@pytest.fixture
def hospital_setup(db):
    roles = {}
    for role_name in ["Admin", "Receptionist", "Doctor", "Lab Assistant"]:
        role = Role(name=role_name)
        db.add(role)
        roles[role_name] = role
    db.flush()

    doctor_one = User(
        full_name="Dr. One",
        username="dr.one",
        password_hash=hash_password("DoctorPass!1"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    doctor_two = User(
        full_name="Dr. Two",
        username="dr.two",
        password_hash=hash_password("DoctorPass!2"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    receptionist = User(
        full_name="Recep One",
        username="recep.one",
        password_hash=hash_password("RecepPass!1"),
        role_id=roles["Receptionist"].id,
        is_active=True,
    )
    admin = User(
        full_name="Admin One",
        username="admin.one",
        password_hash=hash_password("AdminPass!1"),
        role_id=roles["Admin"].id,
        is_active=True,
    )
    lab_assistant = User(
        full_name="Lab Assistant",
        username="lab.assistant",
        password_hash=hash_password("LabPass!123"),
        role_id=roles["Lab Assistant"].id,
        is_active=True,
    )
    db.add_all([doctor_one, doctor_two, receptionist, admin, lab_assistant])
    db.flush()

    db.add_all([
        DoctorProfile(user_id=doctor_one.id, consultation_fee=1200),
        DoctorProfile(user_id=doctor_two.id, consultation_fee=1500),
    ])

    patient_one = Patient(
        patient_id="PAT-AUTH-001",
        patient_name="Patient One (Assigned Dr One)",
        phone="03001111111",
        address="Initial Address 1",
    )
    patient_two = Patient(
        patient_id="PAT-AUTH-002",
        patient_name="Patient Two (Assigned Dr Two)",
        phone="03002222222",
        address="Initial Address 2",
    )
    db.add_all([patient_one, patient_two])
    db.flush()

    visit_one = Visit(
        visit_id="VIS-2026-DR1",
        patient_id=patient_one.id,
        doctor_id=doctor_one.id,
        status="With Doctor",
        priority="Normal",
    )
    visit_two = Visit(
        visit_id="VIS-2026-DR2",
        patient_id=patient_two.id,
        doctor_id=doctor_two.id,
        status="With Doctor",
        priority="Emergency",
    )
    db.add_all([visit_one, visit_two])
    db.flush()

    return {
        "doctor_one": doctor_one,
        "doctor_two": doctor_two,
        "receptionist": receptionist,
        "admin": admin,
        "lab_assistant": lab_assistant,
        "patient_one": patient_one,
        "patient_two": patient_two,
        "visit_one": visit_one,
        "visit_two": visit_two,
    }


def login_helper(client, username, password):
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200
    return res.json()["csrf_token"]


def test_doctor_cannot_transition_another_doctors_visit(client, db, hospital_setup):
    csrf_token = login_helper(client, "dr.one", "DoctorPass!1")

    # Dr. One attempts to transition Dr. Two's visit
    response = client.patch(
        f"/api/v1/patients/visits/{hospital_setup['visit_two'].visit_id}/status",
        headers={"X-CSRF-Token": csrf_token},
        json={"status": "Lab Tests", "reason": "Unauthorized attempt"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Visit not found."

    # Verify database was not changed
    db.refresh(hospital_setup["visit_two"])
    assert hospital_setup["visit_two"].status == "With Doctor"

    history_count = (
        db.query(VisitStatusHistory)
        .filter(VisitStatusHistory.visit_pk == hospital_setup["visit_two"].id)
        .count()
    )
    assert history_count == 0


def test_doctor_can_transition_own_assigned_visit(client, db, hospital_setup):
    csrf_token = login_helper(client, "dr.one", "DoctorPass!1")

    response = client.patch(
        f"/api/v1/patients/visits/{hospital_setup['visit_one'].visit_id}/status",
        headers={"X-CSRF-Token": csrf_token},
        json={"status": "Lab Tests", "reason": "Routine lab order"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Lab Tests"

    db.refresh(hospital_setup["visit_one"])
    assert hospital_setup["visit_one"].status == "Lab Tests"

    history = (
        db.query(VisitStatusHistory)
        .filter(VisitStatusHistory.visit_pk == hospital_setup["visit_one"].id)
        .first()
    )
    assert history is not None
    assert history.changed_by_user_id == hospital_setup["doctor_one"].id
    assert history.from_status == "With Doctor"
    assert history.to_status == "Lab Tests"


def test_invalid_visit_status_transition_is_rejected(client, db, hospital_setup):
    csrf_token = login_helper(client, "dr.one", "DoctorPass!1")

    # Transitioning from "With Doctor" to "With Doctor" is invalid and rejected by workflow
    response = client.patch(
        f"/api/v1/patients/visits/{hospital_setup['visit_one'].visit_id}/status",
        headers={"X-CSRF-Token": csrf_token},
        json={"status": "With Doctor"},
    )

    assert response.status_code == 403
    assert "cannot change a visit" in response.json()["detail"]

    # Verify database remains unchanged
    db.refresh(hospital_setup["visit_one"])
    assert hospital_setup["visit_one"].status == "With Doctor"


def test_doctor_visit_queue_scoped_to_authenticated_doctor(client, hospital_setup):
    # Dr. One should see only visit_one
    login_helper(client, "dr.one", "DoctorPass!1")
    queue_dr_one = client.get("/api/v1/patients/visits/queue").json()

    assert len(queue_dr_one) == 1
    assert queue_dr_one[0]["visit_id"] == hospital_setup["visit_one"].visit_id
    assert queue_dr_one[0]["patient_business_id"] == hospital_setup["patient_one"].patient_id

    # Dr. Two should see only visit_two
    login_helper(client, "dr.two", "DoctorPass!2")
    queue_dr_two = client.get("/api/v1/patients/visits/queue").json()

    assert len(queue_dr_two) == 1
    assert queue_dr_two[0]["visit_id"] == hospital_setup["visit_two"].visit_id
    assert queue_dr_two[0]["patient_business_id"] == hospital_setup["patient_two"].patient_id


def test_doctor_can_search_and_find_assigned_patient(client, hospital_setup):
    login_helper(client, "dr.one", "DoctorPass!1")

    res = client.get(
        "/api/v1/patients/search",
        params={"query": hospital_setup["patient_one"].patient_id},
    )
    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["patient_id"] == hospital_setup["patient_one"].patient_id


def test_doctor_can_update_assigned_patient_address_but_not_phone(client, db, hospital_setup):
    csrf_token = login_helper(client, "dr.one", "DoctorPass!1")

    # Updating permitted field (address)
    res_ok = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"address": "Updated by Doctor One"},
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["address"] == "Updated by Doctor One"

    # Attempting to update phone number as a doctor
    res_phone = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"phone": "03009999888"},
    )
    assert res_phone.status_code == 403
    assert res_phone.json()["detail"] == (
        "Only Receptionists and Admins can update a patient's phone number."
    )

    # Verify phone was not modified
    db.refresh(hospital_setup["patient_one"])
    assert hospital_setup["patient_one"].phone == "03001111111"


def test_receptionist_can_update_phone_and_register_patient(client, db, hospital_setup):
    csrf_token = login_helper(client, "recep.one", "RecepPass!1")

    # Receptionist updates phone
    res_phone = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"phone": "03005555555"},
    )
    assert res_phone.status_code == 200
    assert res_phone.json()["phone"] == "+923005555555"

    # Receptionist registers new patient with visit
    res_reg = client.post(
        "/api/v1/patients/register-with-visit",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "New Registered Patient",
            "phone": "03007777777",
            "doctor_id": hospital_setup["doctor_one"].id,
            "priority": "Normal",
        },
    )
    assert res_reg.status_code == 201
    reg_data = res_reg.json()
    assert reg_data["patient"]["patient_name"] == "New Registered Patient"
    assert reg_data["visit"]["doctor_id"] == hospital_setup["doctor_one"].id


def test_doctor_cannot_register_patient(client, hospital_setup):
    csrf_token = login_helper(client, "dr.one", "DoctorPass!1")

    res = client.post(
        "/api/v1/patients/register-with-visit",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "Doctor Trying to Register",
            "phone": "03008888888",
            "doctor_id": hospital_setup["doctor_one"].id,
            "priority": "Normal",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "You do not have permission to perform this action."


def test_patient_update_normalizes_partial_changes(client, db, hospital_setup):
    csrf_token = login_helper(client, "recep.one", "RecepPass!1")

    response = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"patient_name": "  Updated   Patient   Name  "},
    )

    assert response.status_code == 200
    assert response.json()["patient_name"] == "Updated Patient Name"
    assert response.json()["phone"] == "03001111111"
    assert response.json()["address"] == "Initial Address 1"
    db.refresh(hospital_setup["patient_one"])
    assert hospital_setup["patient_one"].patient_name == "Updated Patient Name"


def test_patient_update_rejects_invalid_and_protected_fields(
    client, db, hospital_setup
):
    csrf_token = login_helper(client, "recep.one", "RecepPass!1")
    url = f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}"

    invalid_name = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={"patient_name": "   "},
    )
    protected_id = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={"patient_id": "PAT-OTHER"},
    )
    protected_primary_key = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={"id": 999},
    )
    protected_cnic = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={"cnic": "3520212345671"},
    )
    invalid_phone = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={"phone": "not a phone"},
    )
    oversized_location = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={"location": "x" * 151},
    )
    empty_update = client.patch(
        url,
        headers={"X-CSRF-Token": csrf_token},
        json={},
    )

    assert invalid_name.status_code == 422
    assert protected_id.status_code == 422
    assert protected_primary_key.status_code == 422
    assert protected_cnic.status_code == 422
    assert invalid_phone.status_code == 422
    assert oversized_location.status_code == 422
    assert empty_update.status_code == 422
    db.refresh(hospital_setup["patient_one"])
    assert hospital_setup["patient_one"].patient_name == (
        "Patient One (Assigned Dr One)"
    )


def test_patient_update_duplicate_phone_rolls_back_all_changes(
    client, db, hospital_setup
):
    csrf_token = login_helper(client, "recep.one", "RecepPass!1")

    response = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "patient_name": "Must Roll Back",
            "phone": hospital_setup["patient_two"].phone,
        },
    )

    assert response.status_code == 409
    assert "IntegrityError" not in response.text
    assert "uq_patients" not in response.text
    db.refresh(hospital_setup["patient_one"])
    assert hospital_setup["patient_one"].patient_name == (
        "Patient One (Assigned Dr One)"
    )
    assert hospital_setup["patient_one"].phone == "03001111111"


def test_patient_update_missing_patient_returns_404(client, hospital_setup):
    csrf_token = login_helper(client, "recep.one", "RecepPass!1")

    response = client.patch(
        "/api/v1/patients/PAT-MISSING",
        headers={"X-CSRF-Token": csrf_token},
        json={"address": "New address"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found."


def test_patient_update_requires_authentication_and_csrf(
    client, hospital_setup
):
    url = f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}"
    payload = {"address": "New address"}

    unauthenticated = client.patch(url, json=payload)
    assert unauthenticated.status_code == 401

    login_helper(client, "recep.one", "RecepPass!1")
    missing_csrf = client.patch(url, json=payload)
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"] == "Missing or invalid CSRF token."


def test_patient_update_forbidden_for_lab_assistant(client, hospital_setup):
    csrf_token = login_helper(client, "lab.assistant", "LabPass!123")

    response = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"address": "Unauthorized"},
    )

    assert response.status_code == 403


def test_admin_can_update_patient_phone(client, hospital_setup):
    csrf_token = login_helper(client, "admin.one", "AdminPass!1")

    response = client.patch(
        f"/api/v1/patients/{hospital_setup['patient_one'].patient_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={"phone": "03005559999"},
    )

    assert response.status_code == 200
    assert response.json()["phone"] == "+923005559999"
