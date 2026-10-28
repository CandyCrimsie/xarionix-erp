"""Lifecycle of fixed anchors. No helper commits: caller owns the transaction."""
from sqlalchemy import or_, select

from core.map_domain import MapOperationError
from core.map_geometry import geometry_token
from core.map_routes import locate_anchor
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from models.map_route_objects import MapRouteObject


async def route_object_rows(session, connection_ids):
    if not connection_ids:
        return []
    return (await session.execute(select(MapRouteObject, MapMarker).join(
        MapMarker, MapMarker.id == MapRouteObject.marker_id
    ).where(MapRouteObject.connection_id.in_(connection_ids)).order_by(MapRouteObject.marker_id))).all()


def describe_route_objects(rows, points):
    result = []
    for attachment, marker in rows:
        state, index, fraction = "on_route", attachment.segment_index, float(attachment.fraction)
        try:
            if points is None:
                raise MapOperationError("route_anchor_conflict", "Нет геометрии")
            index, fraction = locate_anchor(points, marker, attachment)
        except MapOperationError:
            # A direct DBA/import write must not hide a marker or break the
            # entire map. Keep it at its saved point and report the conflict.
            state = "needs_attention"
        result.append({"marker_id": marker.id, "name": marker.name, "point_type": marker.point_type,
            "latitude": float(marker.latitude), "longitude": float(marker.longitude),
            "segment_index": index, "fraction": fraction, "state": state})
    return result


async def reanchor_route(session, current, points, *, visibility=None):
    rows = await route_object_rows(session, [current.id])
    if rows and visibility is not None and visibility != current.visibility:
        raise MapOperationError("route_objects_visibility", "Сначала явно отвяжите объекты трассы перед изменением её видимости.")
    token = geometry_token(points)
    for attachment, marker in rows:
        index, fraction = locate_anchor(points, marker, attachment)
        attachment.segment_index, attachment.fraction, attachment.geometry_token = index, fraction, token
    return rows


async def marker_attachments(session, marker_ids):
    if not marker_ids:
        return {}
    rows = (await session.execute(select(MapRouteObject, MapConnection).join(
        MapConnection, MapConnection.id == MapRouteObject.connection_id
    ).where(MapRouteObject.marker_id.in_(marker_ids)))).all()
    return {a.marker_id: {"connection_id": c.id, "name": c.name, "version": c.version,
        "segment_index": a.segment_index, "fraction": float(a.fraction),
        "geometry_token": a.geometry_token} for a, c in rows}


async def guard_endpoint_position(session, kind, endpoint_id, latitude, longitude):
    """Called while the endpoint row is locked, before its coordinate write.

    Never take a company/connection lock here (the graph writer takes them in
    the opposite order). Check fixed anchors, without exposing private names.
    """
    from services.map_connections import connection_query
    sides = (MapConnection.source_building_id, MapConnection.target_building_id) if kind == "building" else (MapConnection.source_marker_id, MapConnection.target_marker_id)
    query = connection_query().where(or_(*(field == endpoint_id for field in sides)),
        MapConnection.id.in_(select(MapRouteObject.connection_id)))
    for row in (await session.execute(query)).all():
        c, slat, slng, tlat, tlng, *_ = row
        source_match = (c.source_building_id if kind == "building" else c.source_marker_id) == endpoint_id
        target_match = (c.target_building_id if kind == "building" else c.target_marker_id) == endpoint_id
        slat, slng = (latitude, longitude) if source_match else (slat, slng)
        tlat, tlng = (latitude, longitude) if target_match else (tlat, tlng)
        if any(value is None for value in (slat, slng, tlat, tlng)):
            raise MapOperationError("route_anchor_conflict", "Сначала отвяжите объекты от затрагиваемых трасс.")
        points = [[float(slng), float(slat)], *c.vertices, [float(tlng), float(tlat)]]
        for attachment, marker in await route_object_rows(session, [c.id]):
            locate_anchor(points, marker, attachment)
