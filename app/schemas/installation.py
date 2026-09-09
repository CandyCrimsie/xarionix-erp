from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from core.installation import (
    InstallationState,
)

from schemas.user import (
    UserCreate,
)


class InstallationCompanyCreate(
    BaseModel
):
    name: str = Field(
        min_length=1,
        max_length=255,
    )

    short_name: str | None = Field(
        default=None,
        max_length=100,
    )

    @field_validator("name")
    @classmethod
    def normalize_name(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Company name cannot be empty"
            )

        return value

    @field_validator("short_name")
    @classmethod
    def normalize_short_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        return value or None


class InstallationInitializeRequest(
    BaseModel
):
    company: InstallationCompanyCreate
    administrator: UserCreate


class InstallationStatusResponse(
    BaseModel
):
    state: InstallationState
    setup_allowed: bool


class InstallationInitializeResponse(
    BaseModel
):
    state: InstallationState

    company_id: int
    company_name: str

    user_id: int
    username: str

    membership_id: int
    administrator_role_id: int