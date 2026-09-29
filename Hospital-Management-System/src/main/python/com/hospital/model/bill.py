from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Bill:
    bill_id: int
    patient_id: int
    total_amount: Decimal
    status: str = "pending"
