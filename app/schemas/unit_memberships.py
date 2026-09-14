from datetime import datetime
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    model_validator,
)


class UnitMembershipCreate(BaseModel):
    unit_id: int

    is_primary: bool = False


class UnitMembershipUpdate(BaseModel):
    is_primary: bool | None = None

    is_active: bool | None = None


    @model_validator(
        mode="after",
    )
    def validate_primary_state(
        self,
    ) -> Self:
        if (
            self.is_primary is True
            and self.is_active is False
        ):
            raise ValueError(
                "Primary unit membership "
                "must be active"
            )

        return self


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