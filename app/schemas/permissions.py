from pydantic import (
    BaseModel,
    ConfigDict,
)


class PermissionResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    code: str
    name: str
    module: str

    description: str | None

    is_active: bool