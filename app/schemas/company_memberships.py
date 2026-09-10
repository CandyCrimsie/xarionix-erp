from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
)

from models.organizational_units import (
    OrganizationalUnitType,
)


class CompanyMembershipCreate(BaseModel):
    user_id: int

    primary_unit_id: int | None = None


class CompanyMembershipUpdate(BaseModel):
    is_active: bool


class CompanyMembershipResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    user_id: int
    company_id: int

    is_active: bool

    created_at: datetime
    updated_at: datetime


class CompanyMemberSummaryResponse(
    BaseModel
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    user_id: int
    username: str
    user_is_active: bool

    company_id: int

    is_active: bool

    primary_unit_id: int | None
    primary_unit_name: str | None
    primary_unit_type: (
        OrganizationalUnitType | None
    )

    created_at: datetime
    updated_at: datetime