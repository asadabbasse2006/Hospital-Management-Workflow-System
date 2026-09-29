from com.hospital.model.appointment import Appointment


class AppointmentService:
    def __init__(self):
        self._appointments = {}

    def schedule_appointment(self, appointment: Appointment):
        self._appointments[appointment.appointment_id] = appointment
        return appointment

    def get_appointment(self, appointment_id: int):
        return self._appointments.get(appointment_id)
