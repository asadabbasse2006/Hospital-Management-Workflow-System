
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class UserCreate(BaseModel):
    """Fields required to create a staff account."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=2, max_length=150)
    username: str = Field(min_length=3, max_length=100)
    password: SecretStr = Field(min_length=12, max_length=128)
    role_id: int = Field(gt=0)
    department_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Full name cannot be empty.")
        return value

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class UserUpdate(BaseModel):
    """Fields that an administrator may update."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    role_id: int | None = Field(default=None, gt=0)
    department_id: int | None = Field(default=None, gt=0)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = " ".join(value.split())
        if not value:
            raise ValueError("Full name cannot be empty.")
        return value

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return value.strip().lower()


class UserStatusUpdate(BaseModel):
    """Activate or deactivate a staff account."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool


class UserPublic(BaseModel):
    """Safe public representation of a staff account."""

    id: int
    full_name: str
    username: str
    role_id: int
    role: str
    department_id: int | None
    is_active: bool
    created_at: datetime
