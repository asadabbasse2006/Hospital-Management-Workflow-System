INSERT INTO patients (patient_id, first_name, last_name, age, phone, email)
VALUES (1, 'Alice', 'Smith', 30, '1234567890', 'alice@example.com');

INSERT INTO doctors (doctor_id, first_name, last_name, specialty, phone)
VALUES (1, 'John', 'Doe', 'Cardiology', '9876543210');

INSERT INTO appointments (appointment_id, patient_id, doctor_id, appointment_time, status)
VALUES (1, 1, 1, '2026-09-30 10:00:00', 'scheduled');
