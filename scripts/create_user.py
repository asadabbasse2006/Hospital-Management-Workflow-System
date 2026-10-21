import re
from decimal import Decimal, InvalidOperation
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.models import DoctorProfile, Role, User
from app.db.session import SessionLocal
from app.modules.auth.security import hash_password


ALLOWED_ROLES = {
    "Admin",
    "Receptionist",
    "Doctor",
    "Lab Assistant",
    "Pathologist",
    "Pharmacy Assistant",
    "Printing Assistant",
}


def main() -> None:
    username = input("Username: ").strip().lower()

    if not re.fullmatch(r"[a-z0-9._-]{3,100}", username):
        raise SystemExit("Use 3-100 lowercase letters, numbers, '.', '_' or '-'.")

    full_name = input("Full name: ").strip()
    if not full_name:
        raise SystemExit("Full name is required.")

    role_name = input(
        "Role (Receptionist recommended for the first test): "
    ).strip()

    if role_name not in ALLOWED_ROLES:
        raise SystemExit("Invalid role.")

    password = getpass("Password (minimum 12 characters): ")
    confirmation = getpass("Confirm password: ")

    if not 12 <= len(password) <= 128:
        raise SystemExit("Password must be 12-128 characters.")

    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    consultation_fee = None

    if role_name == "Doctor":
        try:
            consultation_fee = Decimal(input("Consultation fee: ").strip())
        except InvalidOperation:
            raise SystemExit("Enter a valid consultation fee.")

        if not consultation_fee.is_finite() or consultation_fee < 0:
            raise SystemExit("Consultation fee must be non-negative.")

    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise SystemExit("Role is missing from the database.")

        if db.scalar(select(User.id).where(User.username == username)):
            raise SystemExit("This username already exists.")

        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role_id=role.id,
            department_id=None,
            is_active=True,
        )

        try:
            db.add(user)
            db.flush()

            if role_name == "Doctor":
                db.add(
                    DoctorProfile(
                        user_id=user.id,
                        consultation_fee=consultation_fee,
                    )
                )

            db.commit()

        except SQLAlchemyError:
            db.rollback()
            raise SystemExit(
                "User creation failed. Check the database and try again."
            )

    print(f"Created user '{username}' with role '{role_name}'.")


if __name__ == "__main__":
    main()