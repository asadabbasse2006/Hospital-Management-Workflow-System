import hashlib

from pwdlib import PasswordHash


password_hasher = PasswordHash.recommended()

DUMMY_PASSWORD_HASH = password_hasher.hash(
    "not-a-real-account-password-for-timing-checks"
)


def hash_password(password: str) -> str:
    """Return a secure password hash."""
    return password_hasher.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hasher.verify(password, stored_hash)
    except (UnknownHashError, ValueError, TypeError):
        return False


def hash_session_token(token: str) -> str:
    """Return the digest stored in the session table."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()