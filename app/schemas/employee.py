import re
from datetime import date, datetime, timezone

from pydantic import BaseModel, EmailStr, Field, field_validator


EMPLOYEE_DETAIL_FIELDS = {
    "first_name", "last_name", "middle_name", "full_name",
    "email", "phone_number", "date_of_birth",
}


class EmployeeDetails(BaseModel):
    """Company-owned employee details, not global login credentials."""

    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=254)
    phone_number: str | None = Field(default=None, max_length=16)
    date_of_birth: date | None = None

    @field_validator("first_name", "last_name", "middle_name", "email", "phone_number", mode="before")
    @classmethod
    def normalize_text(cls, value):
        if isinstance(value, str):
            return " ".join(value.split()) or None
        return value

    @field_validator("first_name", "last_name", "middle_name")
    @classmethod
    def reject_name_controls(cls, value: str | None) -> str | None:
        if value is not None and any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Name contains control characters")
        return value

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone(cls, value):
        if value is None or not isinstance(value, str):
            return value
        normalized = re.sub(r"[\s().-]", "", value)
        if not normalized:
            return None
        if not re.fullmatch(r"\+?[0-9]{7,15}", normalized):
            raise ValueError("Phone must contain 7 to 15 digits and an optional leading +")
        return normalized

    @field_validator("date_of_birth")
    @classmethod
    def reject_future_birth_date(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(timezone.utc).date():
            raise ValueError("Date of birth cannot be in the future")
        return value


class EmployeeDetailsResponse(EmployeeDetails):
    # Read-only legacy value. Never split historical names heuristically.
    full_name: str | None = None


class MyProfileResponse(EmployeeDetailsResponse):
    user_id: int
    username: str
    company_id: int
    company_name: str
    account_created_at: datetime
    joined_at: datetime
