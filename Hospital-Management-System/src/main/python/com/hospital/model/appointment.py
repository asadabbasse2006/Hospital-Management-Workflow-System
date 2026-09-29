from dataclasses import dataclass
from datetime import datetime


@dataclass
class Appointment:
    appointment_id: int
    patient_id: int
    doctor_id: int
    appointment_time: datetime
    status: str = "scheduled"
