from dataclasses import dataclass


@dataclass
class Doctor:
    doctor_id: int
    first_name: str
    last_name: str
    specialty: str | None = None
    phone: str | None = None
