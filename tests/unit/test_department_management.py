
import pytest

from app.core.rate_limit import limiter
from app.db.models import Department, Role, User
from app.modules.auth.security import hash_password


@pytest.fixture(autouse=True)
def reset_rate_limit_storage():
    """Isolate rate-limit storage between tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def department_setup(db):
    """Create an administrator, a doctor, and a department."""
    admin_role = Role(name="Admin")
    doctor_role = Role(name="Doctor")
    db.add_all([admin_role, doctor_role])
    db.flush()

    department = Department(
        name="General Medicine",
        is_active=True,
    )
    db.add(department)
    db.flush()

    admin = User(
        full_name="System Administrator",
        username="admin.department.test",
        password_hash=hash_password("AdminPassword!123"),
        role_id=admin_role.id,
        department_id=department.id,
        is_active=True,
    )
    doctor = User(
        full_name="Test Doctor",
        username="doctor.department.test",
        password_hash=hash_password("DoctorPassword!123"),
        role_id=doctor_role.id,
        department_id=department.id,
        is_active=True,
    )
    db.add_all([admin, doctor])
    db.flush()

    return {
        "admin": admin,
        "doctor": doctor,
        "department": department,
    }


def login_as(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def login_as_admin(client):
    response = login_as(
        client,
        "admin.department.test",
        "AdminPassword!123",
    )
    assert response.status_code == 200, response.text
    return response


def csrf_headers(login_response):
    return {
        "X-CSRF-Token": login_response.json()["csrf_token"]
    }


def test_department_list_requires_authentication(client):
    response = client.get("/api/v1/departments")
    assert response.status_code == 401


def test_non_admin_cannot_list_departments(
    client, department_setup
):
    response = login_as(
        client,
        "doctor.department.test",
        "DoctorPassword!123",
    )
    assert response.status_code == 200, response.text

    response = client.get("/api/v1/departments")
    assert response.status_code == 403


def test_admin_can_list_departments(client, department_setup):
    login_as_admin(client)

    response = client.get("/api/v1/departments")

    assert response.status_code == 200, response.text
    departments = response.json()

    assert len(departments) == 1
    assert departments[0]["name"] == "General Medicine"
    assert departments[0]["is_active"] is True


def test_admin_can_get_department(client, department_setup):
    login_as_admin(client)
    department_id = department_setup["department"].id

    response = client.get(
        f"/api/v1/departments/{department_id}"
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == department_id
    assert response.json()["name"] == "General Medicine"


def test_get_missing_department_returns_404(
    client, department_setup
):
    login_as_admin(client)

    response = client.get("/api/v1/departments/999999")

    assert response.status_code == 404


def test_admin_can_create_department(client, department_setup):
    login_response = login_as_admin(client)

    response = client.post(
        "/api/v1/departments",
        headers=csrf_headers(login_response),
        json={"name": "Clinical Laboratory"},
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["name"] == "Clinical Laboratory"
    assert data["is_active"] is True
    assert "password_hash" not in data


def test_create_department_requires_csrf(
    client, department_setup
):
    login_as_admin(client)

    response = client.post(
        "/api/v1/departments",
        json={"name": "Clinical Laboratory"},
    )

    assert response.status_code == 403


def test_duplicate_department_name_is_rejected(
    client, department_setup
):
    login_response = login_as_admin(client)

    response = client.post(
        "/api/v1/departments",
        headers=csrf_headers(login_response),
        json={"name": "General Medicine"},
    )

    assert response.status_code == 409


def test_department_name_is_normalized(client, department_setup):
    login_response = login_as_admin(client)

    response = client.post(
        "/api/v1/departments",
        headers=csrf_headers(login_response),
        json={"name": "  Clinical   Laboratory  "},
    )

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Clinical Laboratory"


def test_admin_can_rename_department(client, department_setup):
    login_response = login_as_admin(client)
    department_id = department_setup["department"].id

    response = client.patch(
        f"/api/v1/departments/{department_id}",
        headers=csrf_headers(login_response),
        json={"name": "Internal Medicine"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Internal Medicine"


def test_renaming_to_an_existing_name_is_rejected(
    client, department_setup, db
):
    login_response = login_as_admin(client)

    another_department = Department(
        name="Clinical Laboratory",
        is_active=True,
    )
    db.add(another_department)
    db.flush()

    department_id = department_setup["department"].id

    response = client.patch(
        f"/api/v1/departments/{department_id}",
        headers=csrf_headers(login_response),
        json={"name": "Clinical Laboratory"},
    )

    assert response.status_code == 409


def test_admin_can_deactivate_department(
    client, department_setup
):
    login_response = login_as_admin(client)
    department_id = department_setup["department"].id

    response = client.patch(
        f"/api/v1/departments/{department_id}/status",
        headers=csrf_headers(login_response),
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_admin_can_reactivate_department(
    client, department_setup
):
    login_response = login_as_admin(client)
    department_id = department_setup["department"].id

    deactivate_response = client.patch(
        f"/api/v1/departments/{department_id}/status",
        headers=csrf_headers(login_response),
        json={"is_active": False},
    )
    assert deactivate_response.status_code == 200

    reactivate_response = client.patch(
        f"/api/v1/departments/{department_id}/status",
        headers=csrf_headers(login_response),
        json={"is_active": True},
    )

    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["is_active"] is True


def test_department_status_update_requires_csrf(
    client, department_setup
):
    login_as_admin(client)
    department_id = department_setup["department"].id

    response = client.patch(
        f"/api/v1/departments/{department_id}/status",
        json={"is_active": False},
    )

    assert response.status_code == 403


def test_non_admin_cannot_create_department(
    client, department_setup
):
    login_response = login_as(
        client,
        "doctor.department.test",
        "DoctorPassword!123",
    )
    assert login_response.status_code == 200

    response = client.post(
        "/api/v1/departments",
        headers=csrf_headers(login_response),
        json={"name": "Radiology"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": " "},
        {"name": "A"},
        {"name": "Valid Department", "unexpected": "value"},
    ],
)
def test_invalid_department_payload_is_rejected(
    client, department_setup, payload
):
    login_response = login_as_admin(client)

    response = client.post(
        "/api/v1/departments",
        headers=csrf_headers(login_response),
        json=payload,
    )

    assert response.status_code == 422


def test_deactivation_preserves_existing_staff_assignment(
    client, department_setup, db
):
    login_response = login_as_admin(client)
    department = department_setup["department"]
    doctor = department_setup["doctor"]

    response = client.patch(
        f"/api/v1/departments/{department.id}/status",
        headers=csrf_headers(login_response),
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text

    db.refresh(doctor)
    db.refresh(department)

    assert department.is_active is False
    assert doctor.department_id == department.id
