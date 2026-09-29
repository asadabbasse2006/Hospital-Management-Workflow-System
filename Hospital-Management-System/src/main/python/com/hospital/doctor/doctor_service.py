from com.hospital.model.doctor import Doctor


class DoctorService:
    def __init__(self):
        self._doctors = {}

    def add_doctor(self, doctor: Doctor):
        self._doctors[doctor.doctor_id] = doctor
        return doctor

    def get_doctor(self, doctor_id: int):
        return self._doctors.get(doctor_id)
