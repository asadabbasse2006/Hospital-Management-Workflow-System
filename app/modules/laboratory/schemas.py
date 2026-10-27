
# app/modules/laboratory/schemas.py

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LabTestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    category: str | None = None
    specimen_type: str
    description: str | None = None


class LabOrderCreate(BaseModel):
    visit_id: str = Field(min_length=1, max_length=40)
    test_id: int = Field(gt=0)
    clinical_notes: str | None = Field(default=None, max_length=5000)


class LabOrderRead(BaseModel):
    id: int
    visit_id: str
    test_id: int
    test_code: str
    test_name: str
    status: str
    clinical_notes: str | None = None
    created_at: datetime


class LabOrderQueueItem(BaseModel):
    id: int
    visit_id: str
    patient_id: str
    patient_name: str
    test_id: int
    test_code: str
    test_name: str
    specimen_type: str
    status: str
    created_at: datetime
    specimen_collected_at: datetime | None = None
    started_at: datetime | None = None

class LabResultItemCreate(BaseModel):
    """One analyte result entered by laboratory staff."""

    analyte_code: str = Field(min_length=1, max_length=100)
    analyte_name: str = Field(min_length=1, max_length=255)
    result_value: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=50)
    reference_range: str | None = Field(default=None, max_length=255)
    abnormal_flag: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class LabResultsSubmit(BaseModel):
    """Complete batch of results submitted for one laboratory order."""

    results: list[LabResultItemCreate] = Field(min_length=1, max_length=100)


class LabResultRead(BaseModel):
    """Result returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    analyte_code: str
    analyte_name: str
    result_value: str
    unit: str | None = None
    reference_range: str | None = None
    abnormal_flag: bool | None = None
    notes: str | None = None
    entered_by_user_id: int
    entered_at: datetime


class LabResultsSubmitResponse(BaseModel):
    order_id: int
    status: str
    results: list[LabResultRead]


class LabOrderActionResponse(BaseModel):
    order_id: int
    status: str
    action: str
    message: str

class ReleasedLabOrderRead(BaseModel):
    order_id: int
    visit_id: str
    test_id: int
    test_code: str
    test_name: str
    status: str
    created_at: datetime
    results: list[LabResultRead]