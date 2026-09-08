from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
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