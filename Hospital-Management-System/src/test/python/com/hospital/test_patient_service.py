from com.hospital.model.patient import Patient
from com.hospital.patient.patient_service import PatientService


def test_patient_service_get_patient_summary():
    service = PatientService()
    patient = Patient(patient_id=1, first_name="Alice", last_name="Smith")
    service.add_patient(patient)

    result = service.get_patient_summary(1)

    assert result["patient_id"] == 1
    assert result["name"] == "Alice Smith"
    assert result["status"] == "active"
