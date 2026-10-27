import re
from typing import Literal
from datetime import date, datetime
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def normalize_cnic(value: object) -> str | None:
    """Normalize a Pakistani CNIC to 13 digits."""
    if value is None or not str(value).strip():
        return None

    digits = re.sub(r"\D", "", str(value))

    if len(digits) != 13:
        raise ValueError("CNIC must contain exactly 13 digits.")

    return digits


def normalize_phone(value: object) -> str | None:
    """Normalize common Pakistani phone formats to a consistent form."""
    if value is None or not str(value).strip():
        return None

    digits = re.sub(r"\D", "", str(value))

    if not 7 <= len(digits) <= 15:
        raise ValueError("Enter a phone number containing 7–15 digits.")

    # 0092... -> 92...
    if digits.startswith("0092"):
        digits = digits[2:]

    # 0300... -> 92300...
    elif digits.startswith("0") and len(digits) in (10, 11):
        digits = "92" + digits[1:]

    return "+" + digits


class PatientCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    patient_name: str = Field(min_length=1, max_length=150)
    cnic: str | None = Field(default=None, max_length=30)
    father_or_husband_name: str | None = Field(
        default=None, max_length=150
    )
    location: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=30)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=2000)

    @field_validator("patient_name")
    @classmethod
    def normalize_patient_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Patient name is required.")
        return value

    @field_validator(
        "father_or_husband_name",
        "location",
        "gender",
        "address",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None

    @field_validator("cnic", mode="before")
    @classmethod
    def validate_cnic(cls, value):
        return normalize_cnic(value)

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, value):
        return normalize_phone(value)

    @model_validator(mode="after")
    def require_contact_identifier(self):
        if not self.cnic and not self.phone:
            raise ValueError("CNIC or phone number is required.")
        return self


class RegisterPatientWithVisit(PatientCreate):
    doctor_id: int = Field(gt=0)
    priority: str = "Normal"

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value):
        if value not in {"Normal", "Emergency"}:
            raise ValueError("Priority must be Normal or Emergency.")
        return value


class CreateVisitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctor_id: int = Field(gt=0)
    priority: str = "Normal"

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value):
        if value not in {"Normal", "Emergency"}:
            raise ValueError("Priority must be Normal or Emergency.")
        return value


class PatientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: str
    patient_name: str
    cnic: str | None
    father_or_husband_name: str | None
    location: str | None
    phone: str | None
    date_of_birth: date | None
    gender: str | None
    address: str | None
    created_at: datetime


class VisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    visit_id: str
    doctor_id: int
    status: str
    priority: str
    created_at: datetime
    closed_at: datetime | None


class PatientVisitResponse(BaseModel):
    patient: PatientRead
    visit: VisitRead



class PatientUpdateRequest(BaseModel):
    """Fields that can be changed through the patient update endpoint."""

    model_config = ConfigDict(extra="forbid")

    patient_name: str | None = Field(
        default=None, min_length=1, max_length=150
    )
    father_or_husband_name: str | None = Field(
        default=None, max_length=150
    )
    location: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)

    @field_validator(
        "patient_name",
        "father_or_husband_name",
        "location",
        "gender",
        "address",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value):
        if value is None:
            return None
        if not value.strip():
            return None
        return normalize_phone(value)

    @field_validator("patient_name")
    @classmethod
    def validate_patient_name(cls, value):
        if value is None or not value:
            raise ValueError("Patient name cannot be empty.")
        return value



class PatientSearchRead(BaseModel):
    """Minimal patient information for search results."""

    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    patient_name: str
    gender: str | None = None


class VisitStatusTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "With Doctor",
        "Lab Tests",
        "Pharmacy",
        "Printing",
        "Completed",
    ]
    reason: str | None = Field(default=None, max_length=500)



class VisitQueueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    visit_id: str
    patient_business_id: str
    patient_name: str
    doctor_id: int
    status: str
    priority: str
    created_at: datetime
