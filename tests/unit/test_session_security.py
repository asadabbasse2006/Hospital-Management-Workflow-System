from datetime import datetime, timedelta, timezone
import secrets

import pytest

from app.db.models import Role, User, UserSession
from app.modules.auth.dependencies import SESSION_COOKIE_NAME, SESSION_TTL_HOURS
from app.modules.auth.security import hash_password, hash_session_token
from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_auth_rate_limit():
    """Reset in-memory rate-limit state between authentication tests."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()



@pytest.fixture
def create_auth_user(db):
    """Helper to create active or inactive users with a specified role."""
    def _create(
        username="auth.user",
        role_name="Doctor",
        password="ValidPassword!123",
        is_active=True,
    ):
        role = db.query(Role).filter(Role.name == role_name).first()
        if role is None:
            role = Role(name=role_name)
            db.add(role)
            db.flush()

        user = User(
            full_name=f"Full {username}",
            username=username,
            password_hash=hash_password(password),
            role_id=role.id,
            is_active=is_active,
        )
        db.add(user)
        db.flush()
        return user

    return _create


def test_expired_session_is_rejected(client, db, create_auth_user):
    user = create_auth_user(username="expired.user")
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    session_record = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        csrf_token=csrf_token,
        expires_at=past_time,
    )
    db.add(session_record)
    db.flush()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Session is invalid or expired."


def test_revoked_session_is_rejected(client, db, create_auth_user):
    user = create_auth_user(username="revoked.user")
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    future_time = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    session_record = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        csrf_token=csrf_token,
        expires_at=future_time,
        revoked_at=datetime.now(timezone.utc),
    )
    db.add(session_record)
    db.flush()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Session is invalid or expired."


def test_inactive_user_cannot_use_valid_session(client, db, create_auth_user):
    user = create_auth_user(username="inactive.user", is_active=False)
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)

    future_time = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    session_record = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        csrf_token=csrf_token,
        expires_at=future_time,
    )
    db.add(session_record)
    db.flush()

    client.cookies.set(SESSION_COOKIE_NAME, raw_token)
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Session is invalid or expired."


def test_inactive_user_cannot_login(client, create_auth_user):
    create_auth_user(username="inactive.login", is_active=False)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "inactive.login",
            "password": "ValidPassword!123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_unknown_username_cannot_login(client, create_auth_user):
    create_auth_user(username="known.user")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "totally.unknown.user",
            "password": "ValidPassword!123",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_malformed_session_token_is_rejected(client):
    client.cookies.set(SESSION_COOKIE_NAME, "nonexistent-or-malformed-token")
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Session is invalid or expired."


def test_login_does_not_disclose_password_hash_or_secrets(client, create_auth_user):
    create_auth_user(username="safe.user")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "safe.user",
            "password": "ValidPassword!123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "user" in data
    assert "csrf_token" in data
    assert "password_hash" not in data["user"]
    assert "password" not in data["user"]


def test_username_normalization_on_login(client, create_auth_user):
    create_auth_user(username="doctor.case")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "  DOCTOR.CASE  ",
            "password": "ValidPassword!123",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "doctor.case"


def test_session_token_stored_as_hash_not_plaintext(client, db, create_auth_user):
    create_auth_user(username="hash.check.user")

    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "hash.check.user",
            "password": "ValidPassword!123",
        },
    )

    assert response.status_code == 200
    cookie_value = client.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_value is not None

    # Check the database: plaintext cookie value must NOT be found in token_hash
    session_in_db = db.query(UserSession).filter(UserSession.token_hash == cookie_value).first()
    assert session_in_db is None

    # Hash of the cookie must match token_hash in DB
    digest = hash_session_token(cookie_value)
    hashed_session = db.query(UserSession).filter(UserSession.token_hash == digest).first()
    assert hashed_session is not None
