from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"

    __table_args__ = (
        CheckConstraint(
            "consultation_fee >= 0",
            name="consultation_fee_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    consultation_fee: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )


class Patient(Base):
    __tablename__ = "patients"

    __table_args__ = (
        CheckConstraint(
            """
            COALESCE(NULLIF(BTRIM(cnic), ''), '') <> ''
            OR COALESCE(NULLIF(BTRIM(phone), ''), '') <> ''
            """,
            name="patient_has_cnic_or_phone",
        ),
        CheckConstraint(
            "cnic IS NULL OR BTRIM(cnic) <> ''",
            name="cnic_not_blank",
        ),
        CheckConstraint(
            "phone IS NULL OR BTRIM(phone) <> ''",
            name="phone_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Assigned by the application using id_sequences.
    patient_id: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )

    patient_name: Mapped[str] = mapped_column(String(150), nullable=False)
    cnic: Mapped[str | None] = mapped_column(
        String(30), unique=True, nullable=True
    )
    father_or_husband_name: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(
        String(30), unique=True, nullable=True
    )
    date_of_birth: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Appointment(Base):
    __tablename__ = "appointments"

    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending', 'Booked', 'Completed')",
            name="valid_appointment_status",
        ),
        Index(
            "ix_appointments_doctor_status_datetime",
            "doctor_id",
            "status",
            "appointment_datetime",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    appointment_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'Pending'")
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Visit(Base):
    __tablename__ = "visits"

    __table_args__ = (
        CheckConstraint(
            """
            status IN (
                'Visits', 'Lab Tests', 'With Doctor',
                'Pharmacy', 'Printing', 'Receptionist', 'Completed'
            )
            """,
            name="valid_visit_status",
        ),
        CheckConstraint(
            "priority IN ('Normal', 'Emergency')",
            name="valid_visit_priority",
        ),
        Index(
            "ix_visits_doctor_status_priority_created",
            "doctor_id",
            "status",
            "priority",
            "created_at",
        ),
        Index(
            "ix_visits_patient_created",
            "patient_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Assigned by the application using id_sequences.
    visit_id: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    parent_visit_id: Mapped[int | None] = mapped_column(
        ForeignKey("visits.id", ondelete="RESTRICT"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'Receptionist'")
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'Normal'")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IdSequence(Base):
    __tablename__ = "id_sequences"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )