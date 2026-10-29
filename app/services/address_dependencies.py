"""Deletion blockers, scoped for disclosure independently of FK protection.

Address/building rows are shared. Locations and graph objects are not: the
existence of an inaccessible blocker is disclosed, never its count or identity.
Call while holding the deleted row's FOR UPDATE lock; FK remains the last guard.
"""
from sqlalchemy import func, or_, select

from core.map_domain import visible_to
from models.address_objects import AddressObject
from models.buildings import Building
from models.entrances import Entrance
from models.locations import Location
from models.equipment import Equipment
from models.map_connections import MapConnection

TITLES = {"address_object": "Невозможно удалить адресный объект", "building": "Невозможно удалить дом",
    "entrance": "Невозможно удалить подъезд", "location": "Невозможно удалить место размещения",
    "marker": "Невозможно удалить метку с карты", "connection": "Невозможно удалить соединение"}


async def deletion_dependencies(session, kind, object_id, *, company_id=None, user_id=None, allow_empty=False):
    groups = []
    restricted = False

    async def count(model, *where):
        return await session.scalar(select(func.count()).select_from(model).where(*where))

    async def shared(model, type_, *where):
        value = await count(model, *where)
        if value:
            groups.append({"type": type_, "count": value})

    async def locations(*where):
        nonlocal restricted
        total = await count(Location, *where)
        visible = await count(Location, *where, Location.company_id == company_id)
        if visible:
            groups.append({"type": "location", "count": visible})
        restricted |= total > visible

    if kind == "address_object":
        await shared(AddressObject, "address_object", AddressObject.parent_id == object_id)
        await shared(Building, "building", Building.address_object_id == object_id)
    elif kind in {"building", "marker"}:
        if kind == "building":
            await shared(Entrance, "entrance", Entrance.building_id == object_id)
            await locations(Location.building_id == object_id)
        source, target = (MapConnection.source_building_id, MapConnection.target_building_id) if kind == "building" else (MapConnection.source_marker_id, MapConnection.target_marker_id)
        ends = or_(source == object_id, target == object_id)
        visible_filter = visible_to(MapConnection, company_id, user_id)
        total = await count(MapConnection, ends)
        visible = await count(MapConnection, ends, *visible_filter)
        restricted |= total > visible
        if visible:
            # Reuse the canonical endpoint names (building address / marker
            # name). Never query another user's private endpoints for display.
            from services.map_connections import connection_query
            rows = (await session.execute(connection_query().where(ends, *visible_filter)
                .order_by(MapConnection.id).limit(30))).all()
            groups.append({"type": "map_connection", "count": visible, "has_more": visible > len(rows),
                "items": [{"id": row[0].id, "name": row[0].name, "medium": row[0].medium, "status": row[0].status,
                    "source_name": row[-2], "target_name": row[-1]} for row in rows]})
    elif kind == "entrance":
        await locations(Location.entrance_id == object_id)
    elif kind == "location":
        await shared(Equipment, "equipment", Equipment.location_id == object_id)
    elif kind == "connection":
        from models.map_route_objects import MapRouteObject
        from models.map_markers import MapMarker
        query = select(MapMarker).join(MapRouteObject, MapRouteObject.marker_id == MapMarker.id).where(MapRouteObject.connection_id == object_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        query = query.where(*visible_to(MapMarker, company_id, user_id))
        visible = await session.scalar(select(func.count()).select_from(query.subquery()))
        restricted |= total > visible
        if visible:
            rows = (await session.scalars(query.order_by(MapMarker.id).limit(30))).all()
            groups.append({"type": "route_object", "count": visible, "has_more": visible > len(rows),
                "items": [{"id": marker.id, "name": marker.name} for marker in rows]})
    if restricted:
        groups.append({"type": "restricted", "message": "Есть связанные записи, недоступные в текущем контексте. Обратитесь к ответственному за эти объекты."})
    if not groups and not allow_empty:
        # A raced FK violation can roll back a newly inserted dependent row.
        # Don't invent an item/count or claim it is somebody's private record.
        groups.append({"type": "integrity", "message": "Удаление заблокировано ограничением целостности. Обновите данные и повторите проверку."})
    return {"code": "object_has_dependencies", "message": TITLES[kind],
        "object": {"kind": kind, "id": object_id}, "dependencies": groups}
