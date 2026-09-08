from pydantic import (
    BaseModel,
    ConfigDict,
)

from core.permissions.effects import (
    PermissionOverrideEffect,
)
from core.permissions.scopes import (
    PermissionScope,
)


class MembershipPermissionOverrideUpdate(
    BaseModel
):
    effect: PermissionOverrideEffect
    scope: PermissionScope | None = None


class MembershipPermissionOverrideResponse(
    BaseModel
):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    company_membership_id: int
    permission_id: int

    effect: PermissionOverrideEffect
    scope: PermissionScope | None