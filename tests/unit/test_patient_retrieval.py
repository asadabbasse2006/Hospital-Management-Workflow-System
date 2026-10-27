import pytest

from app.core.rate_limit import limiter
from app.db.models import DoctorProfile, Patient, Role, User, Visit
from app.modules.auth.security import hash_password


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def retrieval_setup(db):
    roles = {}
    for role_name in ["Admin", "Receptionist", "Doctor", "Lab Assistant"]:
        role = Role(name=role_name)
        db.add(role)
        roles[role_name] = role
    db.flush()

    receptionist = User(
        full_name="Retrieval Receptionist",
        username="ret.recep",
        password_hash=hash_password("RecepPass!123"),
        role_id=roles["Receptionist"].id,
        is_active=True,
    )
    doctor = User(
        full_name="Retrieval Doctor",
        username="ret.doctor",
        password_hash=hash_password("DoctorPass!123"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    other_doctor = User(
        full_name="Other Retrieval Doctor",
        username="ret.doctor2",
        password_hash=hash_password("DoctorPass!123"),
        role_id=roles["Doctor"].id,
        is_active=True,
    )
    lab_assistant = User(
        full_name="Retrieval Lab Assistant",
        username="ret.lab",
        password_hash=hash_password("LabPass!12345"),
        role_id=roles["Lab Assistant"].id,
        is_active=True,
    )
    db.add_all([receptionist, doctor, other_doctor, lab_assistant])
    db.flush()
    db.add_all(
        [
            DoctorProfile(user_id=doctor.id, consultation_fee=1000),
            DoctorProfile(user_id=other_doctor.id, consultation_fee=1100),
        ]
    )

    assigned = Patient(
        patient_id="PAT-RET-001",
        patient_name="Assigned Search Patient",
        cnic="3520299990001",
        phone="+923009990001",
    )
    unassigned = Patient(
        patient_id="PAT-RET-002",
        patient_name="Unassigned Search Patient",
        cnic="3520299990002",
        phone="+923009990002",
    )
    db.add_all([assigned, unassigned])
    db.flush()

    db.add(
        Visit(
            visit_id="VIS-RET-001",
            patient_id=assigned.id,
            doctor_id=doctor.id,
            status="With Doctor",
            priority="Normal",
        )
    )
    db.flush()

    return {
        "receptionist": receptionist,
        "doctor": doctor,
        "other_doctor": other_doctor,
        "lab_assistant": lab_assistant,
        "assigned": assigned,
        "unassigned": unassigned,
    }


def login_helper(client, username, password="DoctorPass!123"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_get_patient_by_id(client, retrieval_setup):
    login_helper(client, "ret.recep", "RecepPass!123")

    response = client.get(
        f"/api/v1/patients/{retrieval_setup['assigned'].patient_id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["patient_id"] == "PAT-RET-001"
    assert body["patient_name"] == "Assigned Search Patient"
    assert body["cnic"] == "3520299990001"


def test_get_nonexistent_patient_returns_404(client, retrieval_setup):
    login_helper(client, "ret.recep", "RecepPass!123")

    response = client.get("/api/v1/patients/PAT-MISSING")
    assert response.status_code == 404
    assert response.json()["detail"] == "Patient not found."


def test_search_by_patient_id_name_cnic_and_phone(client, retrieval_setup):
    login_helper(client, "ret.recep", "RecepPass!123")

    by_id = client.get(
        "/api/v1/patients/search",
        params={"query": "PAT-RET-001"},
    )
    assert by_id.status_code == 200
    assert [row["patient_id"] for row in by_id.json()] == ["PAT-RET-001"]
    assert set(by_id.json()[0]) == {
        "patient_id",
        "patient_name",
        "gender",
    }

    by_name = client.get(
        "/api/v1/patients/search",
        params={"query": "Assigned Search"},
    )
    assert by_name.status_code == 200
    assert [row["patient_id"] for row in by_name.json()] == ["PAT-RET-001"]

    by_cnic = client.get(
        "/api/v1/patients/search",
        params={"query": "35202-9999000-1"},
    )
    assert by_cnic.status_code == 200
    assert [row["patient_id"] for row in by_cnic.json()] == ["PAT-RET-001"]

    by_phone = client.get(
        "/api/v1/patients/search",
        params={"query": "03009990001"},
    )
    assert by_phone.status_code == 200
    assert [row["patient_id"] for row in by_phone.json()] == ["PAT-RET-001"]


def test_search_returns_empty_list_when_no_matches(client, retrieval_setup):
    login_helper(client, "ret.recep", "RecepPass!123")

    response = client.get(
        "/api/v1/patients/search",
        params={"query": "No Such Patient"},
    )
    assert response.status_code == 200
    assert response.json() == []


def test_search_pagination_and_deterministic_order(client, db, retrieval_setup):
    csrf_token = login_helper(client, "ret.recep", "RecepPass!123")

    created_ids = []
    for index in range(3):
        response = client.post(
            "/api/v1/patients",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "patient_name": f"Pagination Patient {index}",
                "phone": f"03009991{index:03d}",
            },
        )
        assert response.status_code == 201, response.text
        created_ids.append(response.json()["patient_id"])

    page_one = client.get(
        "/api/v1/patients/search",
        params={"query": "Pagination Patient", "offset": 0, "limit": 2},
    )
    page_two = client.get(
        "/api/v1/patients/search",
        params={"query": "Pagination Patient", "offset": 2, "limit": 2},
    )

    assert page_one.status_code == 200
    assert page_two.status_code == 200

    first_ids = [row["patient_id"] for row in page_one.json()]
    second_ids = [row["patient_id"] for row in page_two.json()]

    assert len(first_ids) == 2
    assert len(second_ids) == 1
    assert set(first_ids + second_ids) == set(created_ids)
    assert not set(first_ids) & set(second_ids)

    repeated = client.get(
        "/api/v1/patients/search",
        params={"query": "Pagination Patient", "offset": 0, "limit": 2},
    )
    assert [row["patient_id"] for row in repeated.json()] == first_ids


def test_search_rejects_invalid_pagination_and_query(client, retrieval_setup):
    login_helper(client, "ret.recep", "RecepPass!123")

    empty = client.get("/api/v1/patients/search", params={"query": " "})
    assert empty.status_code == 422

    too_long = client.get(
        "/api/v1/patients/search",
        params={"query": "a" * 101},
    )
    assert too_long.status_code == 422

    bad_limit = client.get(
        "/api/v1/patients/search",
        params={"query": "Assigned", "limit": 0},
    )
    assert bad_limit.status_code == 422

    over_max = client.get(
        "/api/v1/patients/search",
        params={"query": "Assigned", "limit": 101},
    )
    assert over_max.status_code == 422

    negative_offset = client.get(
        "/api/v1/patients/search",
        params={"query": "Assigned", "offset": -1},
    )
    assert negative_offset.status_code == 422


def test_retrieval_requires_authentication(client):
    assert client.get("/api/v1/patients/PAT-RET-001").status_code == 401
    assert (
        client.get(
            "/api/v1/patients/search",
            params={"query": "PAT-RET-001"},
        ).status_code
        == 401
    )


def test_retrieval_forbidden_for_lab_assistant(client, retrieval_setup):
    login_helper(client, "ret.lab", "LabPass!12345")

    get_response = client.get(
        f"/api/v1/patients/{retrieval_setup['assigned'].patient_id}"
    )
    assert get_response.status_code == 403

    search_response = client.get(
        "/api/v1/patients/search",
        params={"query": "PAT-RET-001"},
    )
    assert search_response.status_code == 403


def test_doctor_cannot_retrieve_unassigned_patient(client, retrieval_setup):
    login_helper(client, "ret.doctor")

    missing = client.get(
        f"/api/v1/patients/{retrieval_setup['unassigned'].patient_id}"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Patient not found."

    assigned = client.get(
        f"/api/v1/patients/{retrieval_setup['assigned'].patient_id}"
    )
    assert assigned.status_code == 200
    assert assigned.json()["patient_id"] == "PAT-RET-001"

    search = client.get(
        "/api/v1/patients/search",
        params={"query": "Search Patient"},
    )
    assert search.status_code == 200
    assert [row["patient_id"] for row in search.json()] == ["PAT-RET-001"]


def test_get_patient_does_not_require_csrf(client, retrieval_setup):
    login_helper(client, "ret.recep", "RecepPass!123")

    response = client.get(
        f"/api/v1/patients/{retrieval_setup['assigned'].patient_id}"
    )
    assert response.status_code == 200
