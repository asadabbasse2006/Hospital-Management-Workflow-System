from dataclasses import dataclass


@dataclass
class LabTest:
    test_id: int
    patient_id: int
    test_name: str
    status: str = "ordered"
