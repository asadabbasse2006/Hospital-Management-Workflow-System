class PatientController:
    def __init__(self, patient_service):
        self.patient_service = patient_service

    def create_patient(self, patient):
        return self.patient_service.add_patient(patient)

    def fetch_patient(self, patient_id: int):
        return self.patient_service.get_patient(patient_id)
