class PrescriptionService:
    def __init__(self):
        self._prescriptions = {}

    def add_prescription(self, prescription):
        self._prescriptions[prescription.prescription_id] = prescription
        return prescription
