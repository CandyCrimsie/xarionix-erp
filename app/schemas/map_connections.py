from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.map_markers import BuildingPosition, MapMarkerAppearance, MapMarkerResponse, Visibility, _clean_text


class BuildingEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["building"]
    id: int = Field(gt=0)


class MarkerEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["marker"]
    id: int = Field(gt=0)


MapEndpoint = Annotated[BuildingEndpoint | MarkerEndpoint, Field(discriminator="kind")]
InstallationMethod = Literal["unknown", "aerial", "duct", "direct_buried", "facade", "indoor"]


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
    installation_methods: list[InstallationMethod] | None = Field(default=None, max_length=499)

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
        if self.installation_methods is not None and len(self.installation_methods) != len(self.vertices) + 1:
            raise ValueError("One installation method is required for each geometry segment")
        return self


class MapConnectionUpdate(MapConnectionCreate):
    # A complete draft avoids retaining hidden fields when the medium changes.
    expected_version: int = Field(gt=0)


class RouteNodeMarker(MapMarkerAppearance):
    """Only descriptive/visual fields; topology and ownership are server-owned."""
    icon_name: str | None = "splice"
    point_type: Literal["splice", "fiber_box", "odf", "network_node", "cabinet"] = "splice"
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "description")
    @classmethod
    def clean_text(cls, value, info):
        return _clean_text(value, allow_empty=info.field_name != "name") if value is not None else None


class RoutePointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    expected_version: int = Field(gt=0, strict=True)
    expected_geometry_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    segment_index: int = Field(ge=0, le=498, strict=True)
    fraction: float = Field(ge=0, le=1)
    position: BuildingPosition


class MapConnectionSplit(RoutePointRequest):
    marker: RouteNodeMarker


class RoutePassThroughMarker(RouteNodeMarker):
    point_type: Literal["chamber", "pole", "transition", "fiber_box", "network_node", "cabinet"]
    icon_name: str | None = "chamber"


class MapConnectionPlace(RoutePointRequest):
    marker: RoutePassThroughMarker
    installation_after: InstallationMethod | None = None


class MapInstallationBoundary(RoutePointRequest):
    installation_after: InstallationMethod
    until: Literal["end", "next_vertex"] = "end"


class MapRouteObjectDetach(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0, strict=True)
    expected_geometry_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class BoundarySet(MapRouteObjectDetach):
    operation: Literal["set"]
    installation_after: InstallationMethod


class BoundaryRemove(MapRouteObjectDetach):
    operation: Literal["remove"]
    keep: Literal["previous", "next"]


class BoundaryMove(RoutePointRequest):
    operation: Literal["move"]


MapBoundaryEdit = Annotated[BoundarySet | BoundaryRemove | BoundaryMove, Field(discriminator="operation")]


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
    geometry_token: str
    installation_methods: list[InstallationMethod]
    route_objects: list[dict] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MapConnectionSplitResponse(BaseModel):
    marker: MapMarkerResponse
    connections: tuple[MapConnectionResponse, MapConnectionResponse]


class MapRouteObjectResponse(BaseModel):
    marker: MapMarkerResponse
    connection: MapConnectionResponse


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
