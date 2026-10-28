from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.map_markers import MapMarkerAppearance, Visibility, _clean_text


class BuildingEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["building"]
    id: int = Field(gt=0)


class MarkerEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["marker"]
    id: int = Field(gt=0)


MapEndpoint = Annotated[BuildingEndpoint | MarkerEndpoint, Field(discriminator="kind")]


class MapConnectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source: MapEndpoint
    target: MapEndpoint
    visibility: Visibility = "company"
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    medium: Literal["fiber", "utp"]
    status: Literal["planned", "construction", "active", "inactive"] = "planned"
    fiber_count: int | None = Field(default=None, gt=0, le=10000, strict=True)
    category: Literal["Cat 5e", "Cat 6", "Cat 6A"] | None = None
    vertices: list[tuple[float, float]] = Field(default_factory=list, max_length=498)

    @field_validator("name", "description")
    @classmethod
    def clean_text(cls, value, info):
        return _clean_text(value, allow_empty=info.field_name != "name") if value is not None else None

    @field_validator("vertices")
    @classmethod
    def validate_vertices(cls, value):
        import math
        for lng, lat in value:
            if not (math.isfinite(lng) and math.isfinite(lat) and -180 <= lng <= 180 and -90 <= lat <= 90):
                raise ValueError("Invalid WGS84 coordinate")
        return value

    @model_validator(mode="after")
    def validate_medium_and_ends(self):
        if self.source == self.target:
            raise ValueError("Connection endpoints must be different")
        if (self.medium == "fiber" and self.category is not None) or (self.medium == "utp" and self.fiber_count is not None):
            raise ValueError("Cable parameters do not match medium")
        return self


class MapConnectionUpdate(MapConnectionCreate):
    # A complete draft avoids retaining hidden fields when the medium changes.
    expected_version: int = Field(gt=0)


class EndpointResponse(BaseModel):
    kind: Literal["building", "marker"]
    id: int
    name: str
    latitude: float | None
    longitude: float | None


class MapConnectionResponse(BaseModel):
    id: int
    company_id: int
    owner_user_id: int | None
    visibility: Visibility
    name: str
    description: str | None
    source: EndpointResponse
    target: EndpointResponse
    medium: Literal["fiber", "utp"]
    status: Literal["planned", "construction", "active", "inactive"]
    fiber_count: int | None
    category: str | None
    vertices: list[tuple[float, float]]
    geometry: dict | None
    length_m: float | None
    position_missing: bool
    can_manage: bool
    version: int
    created_at: datetime
    updated_at: datetime


class MapStylePresetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    appearance: MapMarkerAppearance

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return _clean_text(value)


class MapStylePresetUpdate(MapStylePresetCreate):
    expected_version: int = Field(gt=0)


class MapStylePresetResponse(MapStylePresetCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: int
    owner_user_id: int
    version: int
    created_at: datetime
    updated_at: datetime
