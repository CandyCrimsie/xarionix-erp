from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.map_markers import PointType, _clean_text
from schemas.map_connections import InstallationMethod

EntityKind = Literal["building", "marker", "connection"]
LayerMode = Literal["group", "manual", "dynamic"]
ConnectionMode = Literal["hidden", "viewport", "object"]
CableStatus = Literal["planned", "construction", "active", "inactive"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MapTarget(StrictModel):
    kind: EntityKind
    id: int = Field(gt=0, strict=True)


class LayerRules(StrictModel):
    address_object_id: int | None = Field(default=None, gt=0, strict=True)
    point_types: list[PointType] = Field(default_factory=list, max_length=11)
    media: list[Literal["fiber", "utp"]] = Field(default_factory=list, max_length=2)
    statuses: list[CableStatus] = Field(default_factory=list, max_length=4)


class LayerCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: int | None = Field(default=None, gt=0, strict=True)
    mode: LayerMode = "manual"
    sort_order: int = Field(default=0, ge=-1000000, le=1000000, strict=True)
    rules: LayerRules = Field(default_factory=LayerRules)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return _clean_text(value)

    @model_validator(mode="after")
    def rules_match_mode(self):
        has_rules = bool(self.rules.address_object_id or self.rules.point_types or self.rules.media or self.rules.statuses)
        if (self.mode == "dynamic") != has_rules:
            raise ValueError("Dynamic layers require at least one rule; other modes cannot have rules")
        return self


class LayerUpdate(LayerCreate):
    expected_version: int = Field(gt=0, strict=True)


class LayerResponse(LayerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int


class MemberUpdate(StrictModel):
    target: MapTarget
    present: bool
    expected_version: int = Field(gt=0, strict=True)


class LayerMove(StrictModel):
    expected_version: int = Field(gt=0, strict=True)
    direction: Literal[-1, 1]


class MapFilter(StrictModel):
    layers_active: bool = False  # Old clients retain their unfiltered API contract.
    layer_ids: list[Annotated[int, Field(gt=0)]] = Field(default_factory=list, max_length=200)
    include_unassigned: bool = True
    point_types: list[PointType] = Field(default_factory=list, max_length=11)
    point_types_enabled: bool = False
    medium: Literal["all", "fiber", "utp"] = "all"
    status: Literal["all", "planned", "construction", "active", "inactive"] = "all"
    installation: Literal["all", "unknown", "aerial", "duct", "direct_buried", "facade", "indoor"] = "all"


class MapSettings(StrictModel):
    schema_version: Literal[1] = 1
    show_buildings: bool = True
    show_infrastructure: bool = True
    show_personal: bool = True
    point_types: list[PointType] = Field(default_factory=list, max_length=11)
    point_types_enabled: bool = False
    visible_layer_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=200)
    include_unassigned: bool = True
    medium: Literal["all", "fiber", "utp"] = "all"
    status: Literal["all", "planned", "construction", "active", "inactive"] = "all"
    installation: Literal["all", "unknown", "aerial", "duct", "direct_buried", "facade", "indoor"] = "all"
    connection_mode: ConnectionMode = "viewport"


class PreferenceWrite(StrictModel):
    expected_version: int = Field(ge=0, strict=True)
    settings: MapSettings


class PreferenceResponse(StrictModel):
    version: int
    settings: MapSettings
    notice: str | None = None


class GeneralSpecs(StrictModel):
    kind: Literal["general"] = "general"


class BuildingSpecs(StrictModel):
    kind: Literal["building"] = "building"
    floors: int | None = Field(default=None, ge=1, le=300, strict=True)
    premises: int | None = Field(default=None, ge=0, le=100000, strict=True)


class PoleSpecs(StrictModel):
    kind: Literal["pole"] = "pole"
    height_m: float | None = Field(default=None, gt=0, le=100)


class CabinetSpecs(StrictModel):
    kind: Literal["cabinet"] = "cabinet"
    height_u: int | None = Field(default=None, ge=1, le=100, strict=True)


class PassportData(StrictModel):
    inventory_number: str | None = Field(default=None, max_length=80)
    purpose: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=2000)
    commissioned_on: date | None = None
    operational_status: CableStatus | None = None  # Not used for cables: their status already exists.
    specs: Annotated[GeneralSpecs | BuildingSpecs | PoleSpecs | CabinetSpecs, Field(discriminator="kind")] = Field(default_factory=GeneralSpecs)

    @field_validator("inventory_number", "purpose", "note")
    @classmethod
    def clean_text(cls, value):
        return (_clean_text(value, allow_empty=True) or None) if value is not None else None


class PassportWrite(StrictModel):
    expected_version: int = Field(ge=0, strict=True)
    expected_entity_version: int | None = Field(default=None, gt=0, strict=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    status: CableStatus | None = None
    data: PassportData

    @field_validator("name", "description")
    @classmethod
    def clean_text(cls, value, info):
        return _clean_text(value, allow_empty=info.field_name != "name") if value is not None else None
