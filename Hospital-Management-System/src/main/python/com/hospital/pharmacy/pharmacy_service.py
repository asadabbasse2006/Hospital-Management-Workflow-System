class PharmacyService:
    def __init__(self):
        self._stock = {}

    def add_medicine(self, medicine):
        self._stock[medicine.medicine_id] = medicine
        return medicine

    def dispense_medicine(self, medicine_id: int, quantity: int):
        medicine = self._stock.get(medicine_id)
        if medicine is None:
            return {"status": "not_found"}
        medicine.stock_quantity -= quantity
        return {"status": "dispensed", "medicine_id": medicine_id, "remaining_stock": medicine.stock_quantity}
