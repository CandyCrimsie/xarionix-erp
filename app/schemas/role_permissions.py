from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from core.permissions.scopes import (
    PermissionScope,
)


class RolePermissionAssignment(BaseModel):
    permission_id: int = Field(
        gt=0,
    )

    scope: PermissionScope


class RolePermissionsUpdate(BaseModel):
    permissions: list[
        RolePermissionAssignment
    ] = Field(
        default_factory=list,
    )

    @field_validator("permissions")
    @classmethod
    def validate_permissions(
        cls,
        value: list[
            RolePermissionAssignment
        ],
    ) -> list[
        RolePermissionAssignment
    ]:
        permission_ids = [
            item.permission_id
            for item in value
        ]

        if len(permission_ids) != len(
            set(permission_ids)
        ):
            raise ValueError(
                "Permission IDs must be unique"
            )

        return value