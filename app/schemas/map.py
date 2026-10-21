from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MapTileSessionResponse(BaseModel):
    tile_url_template: str
    expires_at: int
    min_zoom: int = 0
    max_zoom: int = 20
    tile_size: int = 256


class MapBuildingProperties(BaseModel):
    id: int
    address_object_id: int
    number: str
    corpus: str | None
    structure: str | None
    full_address: str


class MapPointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class MapBuildingFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int
    geometry: MapPointGeometry
    properties: MapBuildingProperties


class MapBuildingFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[MapBuildingFeature]


class MapBounds(BaseModel):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)


class MapAddressObjectBoundsResponse(BaseModel):
    bounds: MapBounds | None
    building_count: int = Field(ge=0)
