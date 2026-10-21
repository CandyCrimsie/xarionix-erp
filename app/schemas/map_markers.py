from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.map_markers import (
    MAP_MARKER_SHAPES,
    MAP_MARKER_SIZES,
    SUPPORTED_MAP_MARKER_ICONS,
)


HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
MapMarkerSize = Literal["small", "normal", "large"]
MapMarkerShape = Literal["circle", "rounded", "pill", "icon"]


def _clean_text(value: str, *, allow_empty: bool = False) -> str:
    cleaned = " ".join(value.split())
    if not allow_empty and not cleaned:
        raise ValueError("Value cannot be empty")
    if "<" in cleaned or ">" in cleaned:
        raise ValueError("HTML and SVG markup are not allowed")
    return cleaned


class MapMarkerCreate(BaseModel):
    building_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    icon_name: str | None = Field(default="map-pin", max_length=40)
    label_text: str | None = Field(default=None, max_length=80)
    icon_color: str = Field(default="#FFFFFF", pattern=HEX_COLOR_PATTERN)
    icon_opacity: float = Field(default=1, ge=0, le=1)
    text_color: str = Field(default="#FFFFFF", pattern=HEX_COLOR_PATTERN)
    text_opacity: float = Field(default=1, ge=0, le=1)
    background_enabled: bool = True
    background_color: str = Field(default="#2563EB", pattern=HEX_COLOR_PATTERN)
    background_opacity: float = Field(default=0.9, ge=0, le=1)
    border_enabled: bool = True
    border_color: str = Field(default="#FFFFFF", pattern=HEX_COLOR_PATTERN)
    border_width: float = Field(default=2, ge=0, le=8)
    border_opacity: float = Field(default=1, ge=0, le=1)
    marker_opacity: float = Field(default=1, ge=0, le=1)
    marker_size: MapMarkerSize = "normal"
    marker_shape: MapMarkerShape = "rounded"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return _clean_text(value)

    @field_validator("description", "label_text")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean_text(value, allow_empty=True)
        return cleaned or None

    @field_validator("icon_name")
    @classmethod
    def validate_icon(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_MAP_MARKER_ICONS:
            raise ValueError("Unsupported map marker icon")
        return value

    @field_validator("icon_color", "text_color", "background_color", "border_color")
    @classmethod
    def normalize_color(cls, value: str) -> str:
        return value.upper()

    @field_validator("marker_size")
    @classmethod
    def validate_size(cls, value: str) -> str:
        if value not in MAP_MARKER_SIZES:
            raise ValueError("Unsupported map marker size")
        return value

    @field_validator("marker_shape")
    @classmethod
    def validate_shape(cls, value: str) -> str:
        if value not in MAP_MARKER_SHAPES:
            raise ValueError("Unsupported map marker shape")
        return value


class MapMarkerUpdate(BaseModel):
    building_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    icon_name: str | None = Field(default=None, max_length=40)
    label_text: str | None = Field(default=None, max_length=80)
    icon_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    icon_opacity: float | None = Field(default=None, ge=0, le=1)
    text_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    text_opacity: float | None = Field(default=None, ge=0, le=1)
    background_enabled: bool | None = None
    background_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    background_opacity: float | None = Field(default=None, ge=0, le=1)
    border_enabled: bool | None = None
    border_color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    border_width: float | None = Field(default=None, ge=0, le=8)
    border_opacity: float | None = Field(default=None, ge=0, le=1)
    marker_opacity: float | None = Field(default=None, ge=0, le=1)
    marker_size: MapMarkerSize | None = None
    marker_shape: MapMarkerShape | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)

    @field_validator("description", "label_text")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean_text(value, allow_empty=True)
        return cleaned or None

    @field_validator("icon_name")
    @classmethod
    def validate_icon(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_MAP_MARKER_ICONS:
            raise ValueError("Unsupported map marker icon")
        return value

    @field_validator("icon_color", "text_color", "background_color", "border_color")
    @classmethod
    def normalize_color(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "MapMarkerUpdate":
        nullable = {"building_id", "description", "icon_name", "label_text"}
        for field_name in self.model_fields_set - nullable:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class MapMarkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    building_id: int | None
    name: str
    description: str | None
    latitude: float
    longitude: float
    icon_name: str | None
    label_text: str | None
    icon_color: str
    icon_opacity: float
    text_color: str
    text_opacity: float
    background_enabled: bool
    background_color: str
    background_opacity: float
    border_enabled: bool
    border_color: str
    border_width: float
    border_opacity: float
    marker_opacity: float
    marker_size: MapMarkerSize
    marker_shape: MapMarkerShape
    created_at: datetime
    updated_at: datetime
