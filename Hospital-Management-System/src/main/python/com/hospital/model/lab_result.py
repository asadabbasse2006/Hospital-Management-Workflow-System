from dataclasses import dataclass


@dataclass
class LabResult:
    result_id: int
    test_id: int
    result_value: str
    interpretation: str | None = None
