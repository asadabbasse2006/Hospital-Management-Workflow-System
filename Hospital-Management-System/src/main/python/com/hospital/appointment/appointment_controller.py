class AppointmentController:
    def __init__(self, appointment_service):
        self.appointment_service = appointment_service

    def book_appointment(self, appointment):
        return self.appointment_service.schedule_appointment(appointment)
