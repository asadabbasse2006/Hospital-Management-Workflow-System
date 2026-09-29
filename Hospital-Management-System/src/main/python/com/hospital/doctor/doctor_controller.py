class DoctorController:
    def __init__(self, doctor_service):
        self.doctor_service = doctor_service

    def assign_doctor(self, doctor):
        return self.doctor_service.add_doctor(doctor)
