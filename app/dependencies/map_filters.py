from typing import Annotated, Literal

from fastapi import Query

from schemas.map_markers import PointType
from schemas.map_workspace import MapFilter


def map_filters(
    layers_active: bool = False,
    include_unassigned: bool = True,
    layer_ids: Annotated[list[int] | None, Query(max_length=200)] = None,
    point_types: Annotated[list[PointType] | None, Query(max_length=11)] = None,
    point_types_enabled: bool = False,
    medium: Literal["all", "fiber", "utp"] = "all",
    status: Literal["all", "planned", "construction", "active", "inactive"] = "all",
    installation: Literal["all", "unknown", "aerial", "duct", "direct_buried", "facade", "indoor"] = "all",
) -> MapFilter:
    return MapFilter(layers_active=layers_active, include_unassigned=include_unassigned,
        layer_ids=layer_ids or [], point_types=point_types or [], point_types_enabled=point_types_enabled, medium=medium, status=status, installation=installation)
