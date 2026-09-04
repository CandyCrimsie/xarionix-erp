from pydantic import BaseModel


class EffectivePermissionsResponse(BaseModel):
    permissions: list[str]