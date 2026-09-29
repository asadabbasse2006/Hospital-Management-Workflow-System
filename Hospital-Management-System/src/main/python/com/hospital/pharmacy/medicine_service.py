class MedicineService:
    def __init__(self):
        self._medicines = {}

    def register_medicine(self, medicine):
        self._medicines[medicine.medicine_id] = medicine
        return medicine
