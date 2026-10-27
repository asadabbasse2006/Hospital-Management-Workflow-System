import pytest

from app.db.models import DoctorProfile, Patient, Role, User, Visit
from app.db.laboratory_models import LabOrder, LabOrderHistory, LabResult, LabTest
from app.modules.auth.security import hash_password
from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    """Reset in-memory rate-limit state between authentication tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()



@pytest.fixture
def lab_api_setup(db):
    roles = {}
    for r in ["Doctor", "Lab Assistant", "Pathologist", "Receptionist"]:
        role = Role(name=r)
        db.add(role)
        roles[r] = role
    db.flush()

    doctor_one = User(
        full_name="Dr. Alpha",
        username="dr.alpha",
        password_hash=hash_password("DoctorPass!1"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    doctor_two = User(
        full_name="Dr. Beta",
        username="dr.beta",
        password_hash=hash_password("DoctorPass!2"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    assistant = User(
        full_name="Lab Tech",
        username="lab.tech",
        password_hash=hash_password("LabPass!1"),
        role_id=roles["Lab Assistant"].id,
        is_active=True,
    )
    pathologist = User(
        full_name="Dr. Path",
        username="pathologist.user",
        password_hash=hash_password("PathPass!1"),
        role_id=roles["Pathologist"].id,
        is_active=True,
    )
    db.add_all([doctor_one, doctor_two, assistant, pathologist])
    db.flush()

    db.add_all([
        DoctorProfile(user_id=doctor_one.id, consultation_fee=1000),
        DoctorProfile(user_id=doctor_two.id, consultation_fee=1000),
    ])

    patient = Patient(
        patient_id="PAT-LAB-001",
        patient_name="Lab Patient",
        phone="03001234567",
    )
    db.add(patient)
    db.flush()

    visit_alpha = Visit(
        visit_id="VIS-ALPHA-01",
        patient_id=patient.id,
        doctor_id=doctor_one.id,
        status="With Doctor",
        priority="Normal",
    )
    visit_beta = Visit(
        visit_id="VIS-BETA-01",
        patient_id=patient.id,
        doctor_id=doctor_two.id,
        status="With Doctor",
        priority="Normal",
    )
    test = LabTest(
        code="LIPID-TEST",
        name="Lipid Profile",
        category="Biochemistry",
        specimen_type="Serum",
        is_active=True,
    )
    db.add_all([visit_alpha, visit_beta, test])
    db.flush()

    return {
        "doctor_one": doctor_one,
        "doctor_two": doctor_two,
        "assistant": assistant,
        "pathologist": pathologist,
        "patient": patient,
        "visit_alpha": visit_alpha,
        "visit_beta": visit_beta,
        "test": test,
    }


def login_user(client, username, password):
    limiter._storage.reset()
    res = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert res.status_code == 200
    return res.json()["csrf_token"]


def test_doctor_cannot_create_lab_order_for_another_doctors_visit(client, lab_api_setup):
    csrf_token = login_user(client, "dr.alpha", "DoctorPass!1")

    # Dr Alpha tries to order a test for Dr Beta's visit
    response = client.post(
        "/api/v1/laboratory/orders",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "visit_id": lab_api_setup["visit_beta"].visit_id,
            "test_id": lab_api_setup["test"].id,
            "clinical_notes": "Cross-doctor attempt",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Visit not found."


def test_lab_assistant_cannot_create_lab_order(client, lab_api_setup):
    csrf_token = login_user(client, "lab.tech", "LabPass!1")

    response = client.post(
        "/api/v1/laboratory/orders",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "visit_id": lab_api_setup["visit_alpha"].visit_id,
            "test_id": lab_api_setup["test"].id,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "You do not have permission to perform this action."


def test_laboratory_end_to_end_role_authorization_and_release(client, db, lab_api_setup):
    # 1. Doctor creates order for own visit
    doc_csrf = login_user(client, "dr.alpha", "DoctorPass!1")
    order_res = client.post(
        "/api/v1/laboratory/orders",
        headers={"X-CSRF-Token": doc_csrf},
        json={
            "visit_id": lab_api_setup["visit_alpha"].visit_id,
            "test_id": lab_api_setup["test"].id,
            "clinical_notes": "Check cholesterol levels",
        },
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    # 2. Specimen collection:
    # Doctor cannot collect
    doc_collect_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/collect",
        headers={"X-CSRF-Token": doc_csrf},
    )
    assert doc_collect_res.status_code == 403

    # Pathologist cannot collect
    path_csrf = login_user(client, "pathologist.user", "PathPass!1")
    path_collect_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/collect",
        headers={"X-CSRF-Token": path_csrf},
    )
    assert path_collect_res.status_code == 403

    # Lab Assistant collects specimen
    tech_csrf = login_user(client, "lab.tech", "LabPass!1")
    collect_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/collect",
        headers={"X-CSRF-Token": tech_csrf},
    )
    assert collect_res.status_code == 200
    assert collect_res.json()["status"] == "Specimen Collected"

    # 3. Start processing:
    start_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/start",
        headers={"X-CSRF-Token": tech_csrf},
    )
    assert start_res.status_code == 200
    assert start_res.json()["status"] == "In Progress"

    # 4. Result submission:
    # Pathologist cannot submit results
    path_submit_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/results",
        headers={"X-CSRF-Token": path_csrf},
        json={"results": [{"analyte_code": "CHOL", "analyte_name": "Cholesterol", "result_value": "190"}]},
    )
    assert path_submit_res.status_code == 403

    # Lab Assistant submits results
    submit_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/results",
        headers={"X-CSRF-Token": tech_csrf},
        json={
            "results": [
                {
                    "analyte_code": "CHOL",
                    "analyte_name": "Total Cholesterol",
                    "result_value": "195",
                    "unit": "mg/dL",
                    "reference_range": "<200",
                    "abnormal_flag": False,
                },
                {
                    "analyte_code": "TRIG",
                    "analyte_name": "Triglycerides",
                    "result_value": "160",
                    "unit": "mg/dL",
                    "reference_range": "<150",
                    "abnormal_flag": True,
                },
            ]
        },
    )
    assert submit_res.status_code == 201
    assert submit_res.json()["status"] == "Pending Verification"

    # 5. Verification:
    # Lab assistant cannot verify
    tech_verify_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/verify",
        headers={"X-CSRF-Token": tech_csrf},
    )
    assert tech_verify_res.status_code == 403

    # Log in as Pathologist: attempting to release before verification must fail with 409
    path_csrf = login_user(client, "pathologist.user", "PathPass!1")
    premature_release_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/release",
        headers={"X-CSRF-Token": path_csrf},
    )
    assert premature_release_res.status_code == 409
    assert "must be verified before release" in premature_release_res.json()["detail"]

    # Pathologist verifies results
    verify_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/verify",
        headers={"X-CSRF-Token": path_csrf},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["action"] == "RESULTS_VERIFIED"

    # 6. Release:
    # Lab assistant cannot release
    tech_release_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/release",
        headers={"X-CSRF-Token": tech_csrf},
    )
    assert tech_release_res.status_code == 403

    # Pathologist releases results
    release_res = client.post(
        f"/api/v1/laboratory/orders/{order_id}/release",
        headers={"X-CSRF-Token": path_csrf},
    )
    assert release_res.status_code == 200
    assert release_res.json()["action"] == "RESULTS_RELEASED"

    # 7. Doctor access to released results:
    # Dr Beta cannot view Dr Alpha's visit released results (404)
    login_user(client, "dr.beta", "DoctorPass!2")
    unauth_results_res = client.get(
        f"/api/v1/laboratory/visits/{lab_api_setup['visit_alpha'].visit_id}/released-results"
    )
    assert unauth_results_res.status_code == 404
    assert unauth_results_res.json()["detail"] == "Visit not found."

    # Dr Alpha can view own visit released results (200)
    login_user(client, "dr.alpha", "DoctorPass!1")
    auth_results_res = client.get(
        f"/api/v1/laboratory/visits/{lab_api_setup['visit_alpha'].visit_id}/released-results"
    )
    assert auth_results_res.status_code == 200
    released_list = auth_results_res.json()
    assert len(released_list) == 1
    assert released_list[0]["order_id"] == order_id
    assert len(released_list[0]["results"]) == 2


def test_failed_result_submission_does_not_commit_partial_results(client, db, lab_api_setup):
    # Setup order in In Progress state
    order = LabOrder(
        visit_pk=lab_api_setup["visit_alpha"].id,
        test_id=lab_api_setup["test"].id,
        ordered_by_user_id=lab_api_setup["doctor_one"].id,
        status="In Progress",
    )
    db.add(order)
    db.flush()

    tech_csrf = login_user(client, "lab.tech", "LabPass!1")

    # Submit batch with duplicate analyte code (should be rejected with 422)
    response = client.post(
        f"/api/v1/laboratory/orders/{order.id}/results",
        headers={"X-CSRF-Token": tech_csrf},
        json={
            "results": [
                {"analyte_code": "CHOL", "analyte_name": "Cholesterol", "result_value": "180"},
                {"analyte_code": "chol", "analyte_name": "Cholesterol", "result_value": "185"},
            ]
        },
    )
    assert response.status_code == 422

    # Database state verification: 0 results and status still 'In Progress'
    db.refresh(order)
    assert order.status == "In Progress"
    results_in_db = db.query(LabResult).filter(LabResult.order_id == order.id).count()
    assert results_in_db == 0
