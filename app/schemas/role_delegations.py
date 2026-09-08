from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


class RoleDelegationsUpdate(BaseModel):
    assignable_role_ids: list[int] = Field(
        default_factory=list,
    )


class RoleDelegationResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    manager_role_id: int
    assignable_role_id: int