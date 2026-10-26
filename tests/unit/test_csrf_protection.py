import pytest

from app.db.models import Department, DoctorProfile, Patient, Role, User, Visit
from app.db.laboratory_models import LabOrder, LabTest
from app.modules.auth.security import hash_password
from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    """Reset in-memory rate-limit state between authentication tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()



@pytest.fixture
def auth_setup(db):
    """Setup users for various roles with valid passwords."""
    roles = {}
    for role_name in ["Admin", "Receptionist", "Doctor", "Lab Assistant", "Pathologist"]:
        role = Role(name=role_name)
        db.add(role)
        roles[role_name] = role
    db.flush()

    doctor = User(
        full_name="Dr. Test",
        username="csrf.doctor",
        password_hash=hash_password("Password!123"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    receptionist = User(
        full_name="Recep Test",
        username="csrf.receptionist",
        password_hash=hash_password("Password!123"),
        role_id=roles["Receptionist"].id,
        is_active=True,
    )
    assistant = User(
        full_name="Lab Assistant Test",
        username="csrf.lab_assistant",
        password_hash=hash_password("Password!123"),
        role_id=roles["Lab Assistant"].id,
        is_active=True,
    )
    pathologist = User(
        full_name="Pathologist Test",
        username="csrf.pathologist",
        password_hash=hash_password("Password!123"),
        role_id=roles["Pathologist"].id,
        is_active=True,
    )
    db.add_all([doctor, receptionist, assistant, pathologist])
    db.flush()

    doctor_profile = DoctorProfile(user_id=doctor.id, consultation_fee=500)
    db.add(doctor_profile)

    patient = Patient(
        patient_id="PAT-CSRF-001",
        patient_name="CSRF Patient",
        phone="03009999999",
    )
    db.add(patient)
    db.flush()

    visit = Visit(
        visit_id="VIS-CSRF-001",
        patient_id=patient.id,
        doctor_id=doctor.id,
        status="With Doctor",
        priority="Normal",
    )
    lab_test = LabTest(
        code="GLU-TEST",
        name="Glucose Fasting",
        specimen_type="Blood",
        is_active=True,
    )
    db.add_all([visit, lab_test])
    db.flush()

    order = LabOrder(
        visit_pk=visit.id,
        test_id=lab_test.id,
        ordered_by_user_id=doctor.id,
        status="In Progress",
    )
    db.add(order)
    db.flush()

    return {
        "doctor": doctor,
        "receptionist": receptionist,
        "assistant": assistant,
        "pathologist": pathologist,
        "patient": patient,
        "visit": visit,
        "lab_test": lab_test,
        "order": order,
    }


def login_user(client, username):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "Password!123"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_csrf_token_required_on_patient_endpoints(client, auth_setup):
    csrf_token = login_user(client, auth_setup["receptionist"].username)

    # 1. Register patient without CSRF header
    res_no_csrf = client.post(
        "/api/v1/patients/register-with-visit",
        json={
            "patient_name": "Test No CSRF",
            "phone": "03111111111",
            "doctor_id": auth_setup["doctor"].id,
            "priority": "Normal",
        },
    )
    assert res_no_csrf.status_code == 403
    assert res_no_csrf.json()["detail"] == "Missing or invalid CSRF token."

    # 2. Register patient with wrong CSRF header
    res_wrong_csrf = client.post(
        "/api/v1/patients/register-with-visit",
        headers={"X-CSRF-Token": "invalid_csrf_token_value"},
        json={
            "patient_name": "Test Wrong CSRF",
            "phone": "03111111112",
            "doctor_id": auth_setup["doctor"].id,
            "priority": "Normal",
        },
    )
    assert res_wrong_csrf.status_code == 403
    assert res_wrong_csrf.json()["detail"] == "Missing or invalid CSRF token."

    # 3. Create visit for existing patient without CSRF header
    res_visit_no_csrf = client.post(
        f"/api/v1/patients/{auth_setup['patient'].patient_id}/visits",
        json={
            "doctor_id": auth_setup["doctor"].id,
            "priority": "Normal",
        },
    )
    assert res_visit_no_csrf.status_code == 403

    # 4. Update patient record without CSRF header
    res_update_no_csrf = client.patch(
        f"/api/v1/patients/{auth_setup['patient'].patient_id}",
        json={"address": "New Address"},
    )
    assert res_update_no_csrf.status_code == 403

    # 5. Transition visit status without CSRF header
    res_trans_no_csrf = client.patch(
        f"/api/v1/patients/visits/{auth_setup['visit'].visit_id}/status",
        json={"status": "Lab Tests"},
    )
    assert res_trans_no_csrf.status_code == 403


def test_csrf_token_required_on_laboratory_state_changing_endpoints(client, auth_setup):
    # Doctor orders test
    login_user(client, auth_setup["doctor"].username)

    order_no_csrf = client.post(
        "/api/v1/laboratory/orders",
        json={
            "visit_id": auth_setup["visit"].visit_id,
            "test_id": auth_setup["lab_test"].id,
        },
    )
    assert order_no_csrf.status_code == 403
    assert order_no_csrf.json()["detail"] == "Missing or invalid CSRF token."

    # Lab assistant specimen collect / start / submit results
    login_user(client, auth_setup["assistant"].username)
    order_id = auth_setup["order"].id

    collect_no_csrf = client.post(f"/api/v1/laboratory/orders/{order_id}/collect")
    assert collect_no_csrf.status_code == 403

    start_no_csrf = client.post(f"/api/v1/laboratory/orders/{order_id}/start")
    assert start_no_csrf.status_code == 403

    results_no_csrf = client.post(
        f"/api/v1/laboratory/orders/{order_id}/results",
        json={"results": [{"analyte_code": "GLU", "analyte_name": "Glucose", "result_value": "95"}]},
    )
    assert results_no_csrf.status_code == 403

    # Pathologist verify and release
    login_user(client, auth_setup["pathologist"].username)

    verify_no_csrf = client.post(f"/api/v1/laboratory/orders/{order_id}/verify")
    assert verify_no_csrf.status_code == 403

    release_no_csrf = client.post(f"/api/v1/laboratory/orders/{order_id}/release")
    assert release_no_csrf.status_code == 403


def test_read_only_endpoints_do_not_require_csrf_token(client, auth_setup):
    login_user(client, auth_setup["doctor"].username)

    # 1. /auth/me
    assert client.get("/api/v1/auth/me").status_code == 200

    # 2. /patients/search
    assert client.get("/api/v1/patients/search", params={"query": auth_setup["patient"].patient_id}).status_code == 200

    # 3. /patients/visits/queue
    assert client.get("/api/v1/patients/visits/queue").status_code == 200

    # 4. /laboratory/tests
    assert client.get("/api/v1/laboratory/tests").status_code == 200


def test_cross_session_csrf_token_is_rejected(client, db, auth_setup):
    # Log in as doctor
    doc_csrf = login_user(client, auth_setup["doctor"].username)

    # In a separate request, log in as receptionist to get their csrf token
    res_recep = client.post(
        "/api/v1/auth/login",
        json={"username": auth_setup["receptionist"].username, "password": "Password!123"},
    )
    recep_csrf = res_recep.json()["csrf_token"]

    # Re-login as doctor so client cookie is doctor's session
    login_user(client, auth_setup["doctor"].username)

    # Attempt doctor state change using receptionist's CSRF token
    response = client.patch(
        f"/api/v1/patients/{auth_setup['patient'].patient_id}",
        headers={"X-CSRF-Token": recep_csrf},
        json={"address": "Attempted Address with cross-session CSRF"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Missing or invalid CSRF token."

    # Verify database state was NOT changed
    db.refresh(auth_setup["patient"])
    assert auth_setup["patient"].address != "Attempted Address with cross-session CSRF"

