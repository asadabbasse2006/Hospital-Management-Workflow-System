from dataclasses import dataclass


@dataclass
class Prescription:
    prescription_id: int
    patient_id: int
    doctor_id: int
    medicine_name: str
    dosage: str
    instructions: str | None = None
