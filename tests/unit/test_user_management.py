
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
def staff_setup(db):
    """Create roles, a department, and users for API tests."""
    admin_role = Role(name="Admin")
    doctor_role = Role(name="Doctor")
    db.add_all([admin_role, doctor_role])
    db.flush()

    department = Department(name="General Medicine", is_active=True)
    db.add(department)
    db.flush()

    admin = User(
        full_name="System Administrator",
        username="admin.test",
        password_hash=hash_password("AdminPassword!123"),
        role_id=admin_role.id,
        department_id=department.id,
        is_active=True,
    )
    doctor = User(
        full_name="Test Doctor",
        username="doctor.test",
        password_hash=hash_password("DoctorPassword!123"),
        role_id=doctor_role.id,
        department_id=department.id,
        is_active=True,
    )
    db.add_all([admin, doctor])
    db.flush()

    return {
        "admin": admin,
        "admin_role": admin_role,
        "doctor": doctor,
        "doctor_role": doctor_role,
        "department": department,
    }


def login_as(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def login_as_admin(client):
    """Log in as the test administrator and return the response."""
    response = login_as(
        client, "admin.test", "AdminPassword!123"
    )
    assert response.status_code == 200, response.text
    return response


def test_user_list_requires_authentication(client):
    response = client.get("/api/v1/users")
    assert response.status_code == 401


def test_non_admin_cannot_list_users(client, staff_setup):
    response = login_as(
        client, "doctor.test", "DoctorPassword!123"
    )
    assert response.status_code == 200, response.text

    response = client.get("/api/v1/users")
    assert response.status_code == 403


def test_admin_can_list_users_without_exposing_password_hash(
    client, staff_setup
):
    login_as_admin(client)

    response = client.get("/api/v1/users")
    assert response.status_code == 200, response.text

    users = response.json()
    assert len(users) == 2
    assert {user["username"] for user in users} == {
        "admin.test",
        "doctor.test",
    }

    for user in users:
        assert "password_hash" not in user
        assert "password" not in user


def test_admin_can_create_staff_account(client, staff_setup):
    login_response = login_as_admin(client)
    csrf_token = login_response.json()["csrf_token"]

    response = client.post(
        "/api/v1/users",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "full_name": "New Staff Member",
            "username": "new.staff",
            "password": "NewStaffPassword!123",
            "role_id": staff_setup["doctor_role"].id,
            "department_id": staff_setup["department"].id,
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["username"] == "new.staff"
    assert data["full_name"] == "New Staff Member"
    assert data["role"] == "Doctor"
    assert data["department_id"] == staff_setup["department"].id
    assert "password_hash" not in data
    assert "password" not in data


def test_create_staff_requires_csrf(client, staff_setup):
    login_as_admin(client)

    response = client.post(
        "/api/v1/users",
        json={
            "full_name": "New Staff Member",
            "username": "new.staff",
            "password": "NewStaffPassword!123",
            "role_id": staff_setup["doctor_role"].id,
            "department_id": staff_setup["department"].id,
        },
    )

    assert response.status_code == 403


def test_duplicate_username_is_rejected(client, staff_setup):
    login_response = login_as_admin(client)

    response = client.post(
        "/api/v1/users",
        headers={
            "X-CSRF-Token": login_response.json()["csrf_token"]
        },
        json={
            "full_name": "Duplicate Account",
            "username": "doctor.test",
            "password": "AnotherPassword!123",
            "role_id": staff_setup["doctor_role"].id,
        },
    )

    assert response.status_code == 409, response.text


def test_admin_can_update_staff_details(client, staff_setup):
    login_response = login_as_admin(client)
    csrf_token = login_response.json()["csrf_token"]
    doctor_id = staff_setup["doctor"].id

    response = client.patch(
        f"/api/v1/users/{doctor_id}",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "full_name": "Updated Doctor",
            "username": "doctor.updated",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Updated Doctor"
    assert response.json()["username"] == "doctor.updated"


def test_admin_cannot_deactivate_own_account(client, staff_setup):
    login_response = login_as_admin(client)
    csrf_token = login_response.json()["csrf_token"]
    admin_id = staff_setup["admin"].id

    response = client.patch(
        f"/api/v1/users/{admin_id}/status",
        headers={"X-CSRF-Token": csrf_token},
        json={"is_active": False},
    )

    assert response.status_code == 409, response.text


def test_admin_can_deactivate_another_user(client, staff_setup):
    login_response = login_as_admin(client)
    csrf_token = login_response.json()["csrf_token"]
    doctor_id = staff_setup["doctor"].id

    response = client.patch(
        f"/api/v1/users/{doctor_id}/status",
        headers={"X-CSRF-Token": csrf_token},
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False


def test_deactivation_revokes_existing_sessions(
    client, staff_setup, db
):
    doctor = staff_setup["doctor"]

    doctor_login = login_as(
        client, "doctor.test", "DoctorPassword!123"
    )
    assert doctor_login.status_code == 200, doctor_login.text

    # Save the doctor's session cookie before logging in as Admin.
    doctor_cookie = client.cookies.get("hospital_session")
    assert doctor_cookie

    admin_login = login_as_admin(client)
    admin_csrf = admin_login.json()["csrf_token"]

    response = client.patch(
        f"/api/v1/users/{doctor.id}/status",
        headers={"X-CSRF-Token": admin_csrf},
        json={"is_active": False},
    )

    assert response.status_code == 200, response.text

    # Restore the doctor's cookie and verify that it is no longer valid.
    client.cookies.set("hospital_session", doctor_cookie)
    me_response = client.get("/api/v1/auth/me")

    assert me_response.status_code == 401
