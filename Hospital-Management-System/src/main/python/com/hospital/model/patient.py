from dataclasses import dataclass


@dataclass
class Patient:
    patient_id: int
    first_name: str
    last_name: str
    age: int | None = None
    phone: str | None = None
    email: str | None = None
