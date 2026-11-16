# Hospital Management & Laboratory Workflow System

A backend API for managing the real day-to-day workflow of a small hospital and its laboratory: patient registration, doctor visits, lab orders and reports, pharmacy dispensing, and printing. The design is modeled on the actual workflow of a hospital laboratory, not a generic CRUD template.

**Status: early development.** Authentication and patient/visit management are implemented. The remaining modules are scaffolded and planned (see [Roadmap](#roadmap)).

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python) |
| ORM / Migrations | SQLAlchemy 2.x, Alembic |
| Database | PostgreSQL (developed against Neon) |
| Auth | Server-side sessions, argon2 password hashing (`pwdlib`), CSRF tokens |
| Rate limiting | `slowapi` |
| Frontend (planned) | HTML, CSS, JavaScript, Bootstrap |

## Core Workflow

```
Receptionist registers/searches patient -> creates Visit -> assigns Doctor
  -> Doctor consults, orders lab tests and/or prescribes medicine
  -> Lab Assistant collects sample and enters results
  -> Pathologist verifies and finalizes the report
  -> Doctor reviews the report
  -> Pharmacy Assistant dispenses medicine
  -> Printing Assistant prints reports/prescriptions
```

### Key design decisions

- **Patient and Visit are separate entities.** One patient has many visits; tests and prescriptions belong to a visit, not directly to the patient.
- **CNIC is a searchable attribute, not the primary key.** Internal business IDs are generated per entity: `PAT-000182`, `VIS-2026-00451`, and so on.
- **CNIC or phone is required.** Patients under 18 or without a CNIC are identified by phone number.
- **Visits have a priority** (`Normal` or `Emergency`); emergency visits are served first.
- **Roles:** Admin, Receptionist, Doctor, Lab Assistant, Pathologist, Pharmacy Assistant, Printing Assistant.

## Implemented Features

**Authentication and security**
- Login with server-side sessions (8-hour TTL); only a SHA-256 digest of the session token is stored.
- HttpOnly session cookie (`__Host-` prefix and `Secure` flag in production).
- Per-session CSRF token required on state-changing requests (`X-CSRF-Token` header).
- Argon2 password hashing with a dummy-hash check to equalize timing for unknown users.
- Login rate limit of 5 requests per minute.
- Role-based access control via `require_roles(...)`.

**Patients and visits**
- Register a patient and create the first visit in a single transaction.
- Search by Patient ID, CNIC, or phone number.
- Duplicate CNIC/phone prevention.
- Create additional visits for existing patients with doctor assignment and priority.

**Operations**
- `/health/live` and `/health/ready` endpoints (the latter checks the database).
- Alembic migrations and a CLI script for creating users.

## Project Structure

```
app/
  main.py              # FastAPI application entry point
  core/                # config, rate limiting, shared security/permissions
  db/                  # engine/session, declarative base, ORM models
  api/v1/              # API router aggregation
  modules/
    auth/              # login, logout, sessions, CSRF, role checks
    patients/          # registration, search, visit creation
    visits/ appointments/ consultations/ doctor_queue/
    laboratory/        # orders, samples, results, reports, corrections, test catalog
    pharmacy/          # medicines, stock, prescriptions, dispensing
    billing/ printing/ notifications/ audit/ departments/ users/
migrations/            # Alembic migrations
scripts/create_user.py # interactive user creation
docs/project_evidence/ # milestone notes and screenshots
frontend/templates/    # planned UI templates
tests/                 # test suite (to be added)
```

Each module follows a `models / schemas / repository / service / router` layering.

## Getting Started

### Prerequisites

- Python 3.11+
- A PostgreSQL database (a local instance or a [Neon](https://neon.tech) project)

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure the environment

Copy `.env.example` to `.env` and set:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
APP_ENV=development
```

`APP_ENV` defaults to `production`, which makes session cookies secure-only. Set it to `development` when running locally over plain HTTP.

### 3. Run migrations

```bash
alembic upgrade head
```

### 4. Seed roles and create a user

The `roles` table must contain the seven role names listed above before a user can be created. Then run:

```bash
python -m scripts.create_user
```

The script prompts for username, full name, role, and a password of at least 12 characters. For the Doctor role it also asks for a consultation fee.

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

Interactive API docs are available at `http://127.0.0.1:8000/docs`.

## API Overview

All routes are under `/api/v1`.

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/auth/login` | Public (rate limited) | Start a session; returns user and CSRF token |
| GET | `/auth/me` | Authenticated | Current user profile |
| GET | `/auth/csrf` | Authenticated | Current session's CSRF token |
| POST | `/auth/logout` | Authenticated + CSRF | Revoke the session |
| POST | `/patients/register-with-visit` | Receptionist + CSRF | Register a patient and create the first visit |
| GET | `/patients/search?query=` | Authenticated | Search by Patient ID, CNIC, or phone |
| POST | `/patients/{patient_id}/visits` | Receptionist + CSRF | Create a visit for an existing patient |

Health checks: `GET /health/live`, `GET /health/ready`.

## Roadmap

- [x] Authentication, sessions, CSRF, role-based access control
- [x] Patient registration and visit management
- [ ] Doctor queue with tokens and emergency priority
- [ ] Consultations: symptoms, diagnosis, lab test orders, prescriptions
- [ ] Laboratory: samples, result entry, Pathologist verification, corrections
- [ ] Pharmacy: medicine catalog, stock tracking, dispensing
- [ ] Billing at registration, test order, and dispensing
- [ ] Printing queue for reports and prescriptions
- [ ] Notifications and audit log
- [ ] Web frontend (Bootstrap) and Docker setup
- [ ] Automated tests and CI
- [ ] Multi-tenant support for multiple hospitals

## Project Evidence

Milestone notes and screenshots are in [`docs/project_evidence`](docs/project_evidence/milestone_03.md).

## License

No license has been specified yet.
