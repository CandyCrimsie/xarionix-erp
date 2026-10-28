from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.map_markers import SUPPORTED_MAP_MARKER_ICONS

HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"
MapMarkerSize = Literal["small", "normal", "large"]
MapMarkerShape = Literal["circle", "rounded", "pill", "icon"]
Visibility = Literal["company", "private"]
PointType = Literal["building", "network_node", "cabinet", "splice", "pole", "chamber", "equipment", "note", "fiber_box", "odf", "transition"]
BuildingLinkRole = Literal["none", "represents", "located_at", "reference"]


def _clean_text(value: str, *, allow_empty: bool = False) -> str:
    cleaned = " ".join(value.split())
    if not allow_empty and not cleaned:
        raise ValueError("Value cannot be empty")
    if "<" in cleaned or ">" in cleaned:
        raise ValueError("HTML and SVG markup are not allowed")
    return cleaned


class MapMarkerAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    icon_name: str | None = Field(default="note", max_length=40)
    label_text: str | None = Field(default=None, max_length=80)
    icon_color: str = Field(default="#E3EAF3", pattern=HEX_COLOR_PATTERN)
    icon_opacity: float = Field(default=1, ge=0, le=1)
    text_color: str = Field(default="#E3EAF3", pattern=HEX_COLOR_PATTERN)
    text_opacity: float = Field(default=1, ge=0, le=1)
    background_enabled: bool = True
    background_color: str = Field(default="#222E3E", pattern=HEX_COLOR_PATTERN)
    background_opacity: float = Field(default=1, ge=0, le=1)
    border_enabled: bool = True
    border_color: str = Field(default="#3B485A", pattern=HEX_COLOR_PATTERN)
    border_width: float = Field(default=1, ge=0, le=8)
    border_opacity: float = Field(default=1, ge=0, le=1)
    marker_opacity: float = Field(default=1, ge=0, le=1)
    marker_size: MapMarkerSize = "normal"
    marker_shape: MapMarkerShape = "circle"

    @field_validator("label_text")
    @classmethod
    def clean_label(cls, value):
        return (_clean_text(value, allow_empty=True) or None) if value is not None else None

    @field_validator("icon_name")
    @classmethod
    def validate_icon(cls, value):
        if value is not None and value not in SUPPORTED_MAP_MARKER_ICONS:
            raise ValueError("Unsupported map marker icon")
        return value

    @field_validator("icon_color", "text_color", "background_color", "border_color")
    @classmethod
    def normalize_color(cls, value):
        return value.upper()


class BuildingPosition(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class MapMarkerCreate(MapMarkerAppearance):
    building_id: int | None = Field(default=None, gt=0)
    building_link_role: BuildingLinkRole | None = None
    point_type: PointType = "note"
    visibility: Visibility | None = None
    sync_building_coordinates: bool = False
    building_position: BuildingPosition | None = None
    binding_confirmation: str | None = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return _clean_text(value)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value):
        return (_clean_text(value, allow_empty=True) or None) if value is not None else None


class MapMarkerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    expected_version: int | None = Field(default=None, gt=0)
    binding_confirmation: str | None = Field(default=None, max_length=128)
    building_position: BuildingPosition | None = None
    building_id: int | None = Field(default=None, gt=0)
    building_link_role: BuildingLinkRole | None = None
    point_type: PointType | None = None
    visibility: Visibility | None = None
    sync_building_coordinates: bool | None = None
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

    @model_validator(mode="after")
    def validate_fields(self):
        nullable = {"building_id", "description", "icon_name", "label_text", "latitude", "longitude", "building_position", "binding_confirmation"}
        for name in self.model_fields_set - nullable:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        for name in self.model_fields_set & {"name", "description", "label_text"}:
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, _clean_text(value, allow_empty=name != "name") or None)
        if self.icon_name is not None and self.icon_name not in SUPPORTED_MAP_MARKER_ICONS:
            raise ValueError("Unsupported map marker icon")
        return self


class MapMarkerResponse(MapMarkerAppearance):
    model_config = ConfigDict(from_attributes=True, extra="ignore", allow_inf_nan=False)
    id: int
    company_id: int
    owner_user_id: int | None
    visibility: Visibility
    point_type: PointType
    building_link_role: BuildingLinkRole
    building_id: int | None
    building_full_address: str | None = None
    sync_building_coordinates: bool = False
    latitude: float | None
    longitude: float | None
    name: str
    description: str | None
    version: int
    can_manage: bool = False
    route_attachment: dict | None = None
    created_at: datetime
    updated_at: datetime
