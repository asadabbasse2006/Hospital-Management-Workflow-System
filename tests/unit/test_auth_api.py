
import pytest

from app.db.models import Role, User
from app.modules.auth.security import hash_password


@pytest.fixture
def create_user(db):
    """Create a user with a role in the test database."""

    def _create_user(
        username="doctor.test",
        role_name="Doctor",
        is_active=True,
    ):
        role = db.query(Role).filter(Role.name == role_name).first()

        if role is None:
            role = Role(name=role_name)
            db.add(role)
            db.flush()

        user = User(
            full_name="API Test User",
            username=username,
            password_hash=hash_password("TestPassword!123"),
            role_id=role.id,
            is_active=is_active,
        )
        db.add(user)
        db.flush()
        return user

    return _create_user


def login(client, username="doctor.test"):
    return client.post(
        "/api/v1/auth/login",
        json={
            "username": username,
            "password": "TestPassword!123",
        },
    )


def test_login_sets_http_only_session_cookie(client, create_user):
    create_user()

    response = login(client)

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "doctor.test"
    assert response.json()["user"]["role"] == "Doctor"
    assert response.json()["csrf_token"]

    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "hospital_session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie

    # The cookie should authenticate subsequent requests.
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "doctor.test"


def test_invalid_login_is_rejected(client, create_user):
    create_user()

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "doctor.test",
            "password": "WrongPassword!123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_csrf_protected_logout_revokes_session(client, create_user):
    create_user()

    login_response = login(client)
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]

    # Confirm the session's CSRF endpoint returns its associated token.
    csrf_response = client.get("/api/v1/auth/csrf")
    assert csrf_response.status_code == 200
    assert csrf_response.json()["csrf_token"] == csrf_token

    # Logout without a CSRF token must be rejected.
    rejected_response = client.post("/api/v1/auth/logout")
    assert rejected_response.status_code == 403

    # The same session remains valid after the rejected logout.
    assert client.get("/api/v1/auth/me").status_code == 200

    # Logout with the correct CSRF token should succeed.
    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_response.status_code == 200
    assert logout_response.json()["status"] == "logged_out"

    # The revoked session must no longer authenticate requests.
    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401


def test_doctor_cannot_access_lab_order_list(client, create_user):
    create_user(role_name="Doctor")

    login_response = login(client)
    assert login_response.status_code == 200

    response = client.get("/api/v1/laboratory/orders")

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You do not have permission to perform this action."
    )
