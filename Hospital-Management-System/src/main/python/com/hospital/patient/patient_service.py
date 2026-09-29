from com.hospital.model.patient import Patient


class PatientService:
    def __init__(self):
        self._patients = {}

    def add_patient(self, patient: Patient):
        self._patients[patient.patient_id] = patient
        return patient

    def get_patient(self, patient_id: int):
        return self._patients.get(patient_id)

    def get_patient_summary(self, patient_id: int):
        patient = self.get_patient(patient_id)
        if patient is None:
            return {"patient_id": patient_id, "status": "not_found"}
        return {
            "patient_id": patient.patient_id,
            "name": f"{patient.first_name} {patient.last_name}",
            "status": "active",
        }
