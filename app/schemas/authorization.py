from pydantic import BaseModel

from core.permissions.scopes import (
    PermissionScope,
)


class EffectivePermissionsResponse(BaseModel):
    permissions: list[str]

    scopes: dict[
        str,
        PermissionScope,
    ]