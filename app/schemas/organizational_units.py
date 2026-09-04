from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from models.organizational_units import (
    OrganizationalUnitType,
)


class OrganizationalUnitCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=255,
    )

    type: OrganizationalUnitType

    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Organizational unit name cannot be empty"
            )

        return value


class OrganizationalUnitUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    type: OrganizationalUnitType | None = None

    parent_id: int | None = None

    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Organizational unit name cannot be empty"
            )

        return value


class OrganizationalUnitResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    company_id: int
    parent_id: int | None

    name: str
    type: OrganizationalUnitType

    is_active: bool

    created_at: datetime
    updated_at: datetime