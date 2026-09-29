CREATE TABLE IF NOT EXISTS patients (
    patient_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    age INTEGER,
    phone TEXT,
    email TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    doctor_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    specialty TEXT,
    phone TEXT
);

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    appointment_time TEXT NOT NULL,
    status TEXT DEFAULT 'scheduled'
);

CREATE TABLE IF NOT EXISTS lab_tests (
    test_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    test_name TEXT NOT NULL,
    status TEXT DEFAULT 'ordered'
);

CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    instructions TEXT
);

CREATE TABLE IF NOT EXISTS bills (
    bill_id INTEGER PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    total_amount REAL NOT NULL,
    status TEXT DEFAULT 'pending'
);
