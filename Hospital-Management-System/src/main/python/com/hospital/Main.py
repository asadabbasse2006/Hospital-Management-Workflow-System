from com.hospital.patient.patient_service import PatientService


class Main:
    def __init__(self):
        self.patient_service = PatientService()

    def run(self):
        print("Hospital Management System started successfully.")
        print(self.patient_service.get_patient_summary(1))


if __name__ == "__main__":
    Main().run()
