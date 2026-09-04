from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class MembershipRolesUpdate(BaseModel):
    role_ids: list[int] = Field(
        default_factory=list,
    )

    @field_validator("role_ids")
    @classmethod
    def validate_role_ids(
        cls,
        value: list[int],
    ) -> list[int]:
        if any(
            role_id <= 0
            for role_id in value
        ):
            raise ValueError(
                "Role IDs must be positive"
            )

        if len(value) != len(set(value)):
            raise ValueError(
                "Role IDs must be unique"
            )

        return value