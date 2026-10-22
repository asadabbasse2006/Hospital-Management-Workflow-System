from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()


class UserPublic(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    department_id: int | None


class LoginResponse(BaseModel):
    user: UserPublic
    csrf_token: str


class CSRFResponse(BaseModel):
    csrf_token: str