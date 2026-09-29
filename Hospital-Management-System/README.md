# Hospital Management System

A Python-based hospital management system with modules for patient management, appointments, laboratory services, pharmacy operations, billing, and data utilities.

## Project structure

- `src/main/python/com/hospital` contains the application code
- `src/test/python` contains test cases
- `resources` contains configuration and SQL scripts

## Run the application

```bash
cd Hospital-Management-System
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src/main/python python src/main/python/com/hospital/Main.py
```

## Modules

- Patient management
- Doctor management
- Appointment scheduling
- Laboratory testing and results
- Pharmacy and prescriptions
- Billing and invoice logic
- Database connection and utilities
