from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class CompanyChildCreate(BaseModel):
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


class CompanyRootCreate(
    CompanyChildCreate
):
    pass


class CompanyCreate(
    CompanyChildCreate
):
    parent_id: int | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )

    short_name: str | None = Field(
        default=None,
        max_length=100,
    )

    parent_id: int | None = None

    is_active: bool | None = None


    @field_validator("name")
    @classmethod
    def normalize_name(
        cls,
        value: str | None,
    ) -> str:
        if value is None:
            raise ValueError(
                "Company name cannot be null"
            )

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


class CompanyResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    parent_id: int | None

    name: str
    short_name: str | None

    is_active: bool

    created_at: datetime
    updated_at: datetime


class CompanyTreeNodeResponse(
    CompanyResponse
):
    children: list[
        "CompanyTreeNodeResponse"
    ] = Field(
        default_factory=list,
    )


class CompanyMoveRequest(
    BaseModel
):
    parent_id: int = Field(
        gt=0,
    )


class CompanyActivationRequest(
    BaseModel
):
    is_active: bool