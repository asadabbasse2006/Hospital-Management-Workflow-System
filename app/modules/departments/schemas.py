
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())

        if not value:
            raise ValueError("Department name cannot be empty.")

        return value


class DepartmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = " ".join(value.split())

        if not value:
            raise ValueError("Department name cannot be empty.")

        return value


class DepartmentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class DepartmentPublic(BaseModel):
    id: int
    name: str
    is_active: bool
