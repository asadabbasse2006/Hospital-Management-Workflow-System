class Validation:
    @staticmethod
    def is_valid_phone(phone: str | None) -> bool:
        if not phone:
            return True
        return len(phone) >= 7

    @staticmethod
    def is_valid_email(email: str | None) -> bool:
        if not email:
            return True
        return "@" in email and "." in email
