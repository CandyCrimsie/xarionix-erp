from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
)


class UnitMembershipCreate(BaseModel):
    unit_id: int

    is_primary: bool = False


class UnitMembershipUpdate(BaseModel):
    is_primary: bool | None = None

    is_active: bool | None = None


class UnitMembershipResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    company_membership_id: int
    unit_id: int

    is_primary: bool
    is_active: bool

    created_at: datetime
    updated_at: datetime