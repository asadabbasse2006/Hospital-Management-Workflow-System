from dataclasses import dataclass


@dataclass
class Medicine:
    medicine_id: int
    name: str
    stock_quantity: int
    unit_price: float
