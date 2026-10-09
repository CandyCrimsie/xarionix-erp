from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from core.address_normalization import (
    clean_address_value,
    clean_optional_address_value,
)
from models.address_types import AddressTypeCategory


class AddressTypeCreate(BaseModel):
    code: str = Field(
        min_length=1,
        max_length=50,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    category: AddressTypeCategory
    name: str = Field(min_length=1, max_length=100)
    short_name: str | None = Field(default=None, max_length=30)
    sort_order: int = Field(default=100, ge=0, le=10000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = clean_address_value(value)
        if not value:
            raise ValueError("Address type name cannot be empty")
        return value

    @field_validator("short_name")
    @classmethod
    def normalize_short_name(
        cls,
        value: str | None,
    ) -> str | None:
        return clean_optional_address_value(value)


class AddressTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    short_name: str | None = Field(default=None, max_length=30)
    sort_order: int | None = Field(default=None, ge=0, le=10000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = clean_address_value(value)
        if not value:
            raise ValueError("Address type name cannot be empty")
        return value

    @field_validator("short_name")
    @classmethod
    def normalize_short_name(
        cls,
        value: str | None,
    ) -> str | None:
        return clean_optional_address_value(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "AddressTypeUpdate":
        for field in ("name", "sort_order"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AddressTypeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    category: AddressTypeCategory
    name: str
    short_name: str | None
    sort_order: int
    is_system: bool
    created_at: datetime
    updated_at: datetime


class AddressObjectCreate(BaseModel):
    parent_id: int | None = None
    type_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = clean_address_value(value)
        if not value:
            raise ValueError("Address object name cannot be empty")
        return value


class AddressObjectUpdate(BaseModel):
    parent_id: int | None = None
    type_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = clean_address_value(value)
        if not value:
            raise ValueError("Address object name cannot be empty")
        return value

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "AddressObjectUpdate":
        for field in ("name", "type_id"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AddressObjectResponse(BaseModel):
    id: int
    parent_id: int | None
    type_id: int
    type_code: str
    type_category: AddressTypeCategory
    type_name: str
    type_short_name: str | None
    name: str
    created_at: datetime
    updated_at: datetime


class AddressObjectTreeResponse(AddressObjectResponse):
    children: list[AddressObjectTreeResponse] = Field(default_factory=list)


class BuildingCreate(BaseModel):
    address_object_id: int = Field(gt=0)
    number: str = Field(min_length=1, max_length=50)
    corpus: str | None = Field(default=None, max_length=50)
    structure: str | None = Field(default=None, max_length=50)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    @field_validator("number")
    @classmethod
    def normalize_number(cls, value: str) -> str:
        value = clean_address_value(value)
        if not value:
            raise ValueError("Building number cannot be empty")
        return value

    @field_validator("corpus", "structure")
    @classmethod
    def normalize_optional_part(
        cls,
        value: str | None,
    ) -> str | None:
        return clean_optional_address_value(value)


class BuildingUpdate(BaseModel):
    address_object_id: int | None = Field(default=None, gt=0)
    number: str | None = Field(default=None, min_length=1, max_length=50)
    corpus: str | None = Field(default=None, max_length=50)
    structure: str | None = Field(default=None, max_length=50)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)

    @field_validator("number")
    @classmethod
    def normalize_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = clean_address_value(value)
        if not value:
            raise ValueError("Building number cannot be empty")
        return value

    @field_validator("corpus", "structure")
    @classmethod
    def normalize_optional_part(
        cls,
        value: str | None,
    ) -> str | None:
        return clean_optional_address_value(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "BuildingUpdate":
        for field in ("address_object_id", "number"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class BuildingResponse(BaseModel):
    id: int
    address_object_id: int
    number: str
    corpus: str | None
    structure: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    full_address: str
    created_at: datetime
    updated_at: datetime


class EntranceCreate(BaseModel):
    number: str = Field(min_length=1, max_length=20)

    @field_validator("number")
    @classmethod
    def normalize_number(cls, value: str) -> str:
        value = clean_address_value(value)
        if not value:
            raise ValueError("Entrance number cannot be empty")
        return value


class EntranceUpdate(EntranceCreate):
    pass


class EntranceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: int
    number: str
    created_at: datetime
    updated_at: datetime


class LocationCreate(BaseModel):
    building_id: int = Field(gt=0)
    entrance_id: int | None = Field(default=None, gt=0)
    floor: str | None = Field(default=None, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = clean_address_value(value)
        if not value:
            raise ValueError("Location name cannot be empty")
        return value

    @field_validator("floor", "description")
    @classmethod
    def normalize_optional_value(
        cls,
        value: str | None,
    ) -> str | None:
        return clean_optional_address_value(value)


class LocationUpdate(BaseModel):
    building_id: int | None = Field(default=None, gt=0)
    entrance_id: int | None = Field(default=None, gt=0)
    floor: str | None = Field(default=None, max_length=20)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = clean_address_value(value)
        if not value:
            raise ValueError("Location name cannot be empty")
        return value

    @field_validator("floor", "description")
    @classmethod
    def normalize_optional_value(
        cls,
        value: str | None,
    ) -> str | None:
        return clean_optional_address_value(value)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "LocationUpdate":
        for field in ("building_id", "name"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    building_id: int
    entrance_id: int | None
    floor: str | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class AddressSearchResponse(BaseModel):
    items: list[BuildingResponse]
    total: int
    limit: int
    offset: int
