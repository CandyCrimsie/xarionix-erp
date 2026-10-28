"""Typed graph endpoints. Routes are assembled in SQL from current positions.

There is no materialized endpoint geometry to invalidate on a point move.
PostgreSQL's built-in lseg/box intersection handles crossing viewport edges.
"""
import math

from sqlalchemy import Float, and_, bindparam, case, func, literal, or_, select, text, union_all
from sqlalchemy.orm import aliased

from core.map_domain import MapOperationError, check_version, lock_map_company, require_write, visible_to
from core.map_geometry import geometry_token, segment_position
from models.buildings import Building
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from models.map_style_presets import MapMarkerStylePreset
from repositories.addresses import _building_record_select
from repositories.map_markers import get_map_marker
from schemas.map_connections import EndpointResponse, MapConnectionResponse, MapStylePresetResponse
from services.building_coordinates import lock_buildings


def connection_query():
    buildings = _building_record_select().subquery("building_addresses")
    sb, tb = buildings.alias("source_building"), buildings.alias("target_building")
    sm, tm = aliased(MapMarker), aliased(MapMarker)
    s_lat = case((MapConnection.source_building_id.is_not(None), sb.c.latitude), else_=sm.latitude)
    s_lng = case((MapConnection.source_building_id.is_not(None), sb.c.longitude), else_=sm.longitude)
    t_lat = case((MapConnection.target_building_id.is_not(None), tb.c.latitude), else_=tm.latitude)
    t_lng = case((MapConnection.target_building_id.is_not(None), tb.c.longitude), else_=tm.longitude)
    return select(
        MapConnection,
        s_lat.label("source_latitude"), s_lng.label("source_longitude"),
        t_lat.label("target_latitude"), t_lng.label("target_longitude"),
        func.coalesce(sb.c.full_address, sm.name).label("source_name"),
        func.coalesce(tb.c.full_address, tm.name).label("target_name"),
    ).outerjoin(sb, sb.c.id == MapConnection.source_building_id).outerjoin(
        tb, tb.c.id == MapConnection.target_building_id
    ).outerjoin(sm, sm.id == MapConnection.source_marker_id).outerjoin(tm, tm.id == MapConnection.target_marker_id)


def route_length(points):
    length = 0.0
    for (lng1, lat1), (lng2, lat2) in zip(points, points[1:]):
        lat1, lat2 = math.radians(lat1), math.radians(lat2)
        delta_lat, delta_lng = lat2 - lat1, math.radians(lng2 - lng1)
        angle = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
        length += 6371008.8 * 2 * math.asin(min(1, math.sqrt(max(0, angle))))
    return length


def connection_response(row, *, user_id, can_manage):
    c, slat, slng, tlat, tlng, sname, tname = row
    missing = any(value is None for value in (slat, slng, tlat, tlng))
    points = None if missing else [[float(slng), float(slat)], *c.vertices, [float(tlng), float(tlat)]]
    values = {column.name: getattr(c, column.name) for column in MapConnection.__table__.columns}
    return MapConnectionResponse(
        **{key: value for key, value in values.items() if key not in {"source_building_id", "target_building_id", "source_marker_id", "target_marker_id"}},
        source=EndpointResponse(kind="building" if c.source_building_id else "marker", id=c.source_building_id or c.source_marker_id, name=sname or "Объект без расположения", latitude=slat, longitude=slng),
        target=EndpointResponse(kind="building" if c.target_building_id else "marker", id=c.target_building_id or c.target_marker_id, name=tname or "Объект без расположения", latitude=tlat, longitude=tlng),
        geometry={"type": "LineString", "coordinates": points} if points else None,
        length_m=route_length(points) if points else None,
        position_missing=missing,
        geometry_token=geometry_token(points),
        can_manage=c.owner_user_id == user_id if c.visibility == "private" else can_manage,
    )


async def get_connection(session, *, company_id, user_id, can_manage, connection_id):
    row = (await session.execute(connection_query().where(
        MapConnection.id == connection_id, *visible_to(MapConnection, company_id, user_id)
    ).execution_options(populate_existing=True))).one_or_none()
    if row is None:
        raise MapOperationError("not_found", "Соединение не найдено", status=404)
    return connection_response(row, user_id=user_id, can_manage=can_manage)


def connection_list_query(*, company_id, user_id, bounds=None, endpoint_kind=None, endpoint_id=None):
    query = connection_query().where(*visible_to(MapConnection, company_id, user_id))
    if endpoint_id is not None:
        fields = (MapConnection.source_building_id, MapConnection.target_building_id) if endpoint_kind == "building" else (MapConnection.source_marker_id, MapConnection.target_marker_id)
        query = query.where(or_(*(field == endpoint_id for field in fields)))
    if bounds:
        # Construct one ordered list with endpoints + internal vertices. The
        # EXISTS predicate checks each actual segment, not just its bounding box.
        rows = query.cte("visible_connections")
        query = select(rows).where(text("""
            EXISTS (
                SELECT 1 FROM (
                    SELECT value, lead(value) OVER (ORDER BY ordinal) AS next
                    FROM jsonb_array_elements(
                        jsonb_build_array(jsonb_build_array(source_longitude, source_latitude))
                        || vertices || jsonb_build_array(jsonb_build_array(target_longitude, target_latitude))
                    ) WITH ORDINALITY AS points(value, ordinal)
                ) segments
                WHERE segments.next IS NOT NULL AND
                    lseg(point((value->>0)::float8, (value->>1)::float8),
                         point((next->>0)::float8, (next->>1)::float8))
                    ?# box(point(:west, :south), point(:east, :north))
            )
        """).bindparams(*(bindparam(key, type_=Float) for key in ("west", "east", "south", "north"))))
        # Restore ORM entity processing after the CTE instead of loading all
        # rows and matching in Python.
        ids = query.with_only_columns(rows.c.id)
        query = connection_query().where(MapConnection.id.in_(ids)).params(**bounds)
    return query.order_by(MapConnection.id).limit(2001)


async def get_connections(session, *, company_id, user_id, can_manage, bounds=None, endpoint_kind=None, endpoint_id=None):
    query = connection_list_query(company_id=company_id, user_id=user_id, bounds=bounds, endpoint_kind=endpoint_kind, endpoint_id=endpoint_id)
    rows = (await session.execute(query)).all()
    if len(rows) > 2000:
        raise MapOperationError("viewport_too_large", "Слишком много соединений. Увеличьте масштаб.", status=422)
    return [connection_response(row, user_id=user_id, can_manage=can_manage) for row in rows]


async def _endpoint(session, endpoint, *, company_id, user_id, visibility):
    if endpoint.kind == "building":
        entity = await session.get(Building, endpoint.id)
        if entity is None:
            raise MapOperationError("endpoint_not_found", "Конец соединения не найден", status=404)
        return "building", entity
    marker = await get_map_marker(session, company_id=company_id, user_id=user_id, marker_id=endpoint.id)
    if marker is None:
        raise MapOperationError("endpoint_not_found", "Конец соединения не найден", status=404)
    if visibility == "company" and marker.visibility != "company":
        raise MapOperationError("private_endpoint", "Общее соединение не может ссылаться на личную отметку.", status=422)
    if marker.building_link_role == "represents":
        return "building", await session.get(Building, marker.building_id)
    return "marker", marker


async def save_connection(session, *, company_id, user_id, can_manage, data, connection_id=None):
    try:
        await lock_map_company(session, company_id)
        current = await session.scalar(select(MapConnection).where(
            MapConnection.id == connection_id, *visible_to(MapConnection, company_id, user_id)
        ).with_for_update()) if connection_id else None
        if connection_id and current is None:
            raise MapOperationError("not_found", "Соединение не найдено", status=404)
        if current:
            require_write(current, user_id, can_manage)
            check_version(current, data.expected_version)
        if data.visibility == "company" and not can_manage:
            raise MapOperationError("permission_denied", "Нет права управлять общими соединениями", status=403)
        # Ownership never comes from the request. Publishing a private route
        # requires manage and revalidates every endpoint in the new visibility.
        source_kind, source = await _endpoint(session, data.source, company_id=company_id, user_id=user_id, visibility=data.visibility)
        target_kind, target = await _endpoint(session, data.target, company_id=company_id, user_id=user_id, visibility=data.visibility)
        await lock_buildings(session, {e.id for kind, e in ((source_kind, source), (target_kind, target)) if kind == "building"})
        for kind, endpoint in ((source_kind, source), (target_kind, target)):
            await session.refresh(endpoint, with_for_update=True)
        if source_kind == target_kind and source.id == target.id:
            raise MapOperationError("same_endpoint", "Выберите два разных объекта.", status=422)
        if any(e.latitude is None or e.longitude is None for e in (source, target)):
            raise MapOperationError("missing_position", "Сначала задайте расположение обоих концов соединения.", status=422)
        points = [[float(source.longitude), float(source.latitude)], *data.vertices, [float(target.longitude), float(target.latitude)]]
        if route_length(points) < 0.01:
            raise MapOperationError("zero_length", "Трасса не может иметь нулевую длину.", status=422)
        values = data.model_dump(exclude={"source", "target", "expected_version"})
        values.update(owner_user_id=user_id if data.visibility == "private" else None)
        for side, kind, endpoint in (("source", source_kind, source), ("target", target_kind, target)):
            values[f"{side}_building_id"] = endpoint.id if kind == "building" else None
            values[f"{side}_marker_id"] = endpoint.id if kind == "marker" else None
        if current:
            for key, value in values.items():
                setattr(current, key, value)
            current.version += 1
        else:
            current = MapConnection(company_id=company_id, **values)
            session.add(current)
        await session.flush()
        saved_id = current.id
        await session.commit()
        return await get_connection(session, company_id=company_id, user_id=user_id, can_manage=can_manage, connection_id=saved_id)
    except Exception:
        await session.rollback()
        raise


async def delete_connection(session, *, company_id, user_id, can_manage, connection_id):
    try:
        await lock_map_company(session, company_id)
        entity = await session.scalar(select(MapConnection).where(
            MapConnection.id == connection_id, *visible_to(MapConnection, company_id, user_id)
        ).with_for_update())
        if entity is None:
            raise MapOperationError("not_found", "Соединение не найдено", status=404)
        require_write(entity, user_id, can_manage)
        await session.delete(entity)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def split_connection(session, *, company_id, user_id, can_manage, connection_id, data):
    """One company lock + endpoint row locks, one commit, no intermediate CRUD commits.

    Keep the original ID for A→M. No other table references connection IDs;
    the new M→B inherits all cable, visibility and ownership attributes.
    """
    from services.map_markers import get_marker
    from schemas.map_connections import MapConnectionSplitResponse

    try:
        await lock_map_company(session, company_id)
        current = await session.scalar(select(MapConnection).where(
            MapConnection.id == connection_id, *visible_to(MapConnection, company_id, user_id)
        ).with_for_update().execution_options(populate_existing=True))
        if current is None:
            raise MapOperationError("not_found", "Соединение не найдено", status=404)
        require_write(current, user_id, can_manage)
        check_version(current, data.expected_version)
        # A splice is a technical object, not a personal note. Keep the same
        # addresses.manage rule as ordinary marker creation, even on private lines.
        if not can_manage:
            raise MapOperationError("permission_denied", "Для создания муфты требуется право управления адресами.", status=403)
        await lock_buildings(session, {i for i in (current.source_building_id, current.target_building_id) if i})
        marker_ids = {i for i in (current.source_marker_id, current.target_marker_id) if i}
        if marker_ids:
            await session.execute(select(MapMarker).where(MapMarker.id.in_(marker_ids)).order_by(MapMarker.id).with_for_update())
        snapshot = await get_connection(session, company_id=company_id, user_id=user_id, can_manage=can_manage, connection_id=connection_id)
        if snapshot.geometry_token != data.expected_geometry_token:
            raise MapOperationError("stale_geometry", "Расположение концов трассы изменилось. Обновите соединение и выберите точку заново.")
        if snapshot.geometry is None:
            raise MapOperationError("missing_position", "У концов трассы отсутствуют координаты.", status=422)
        points = snapshot.geometry["coordinates"]
        index = data.segment_index
        if index >= len(points) - 1:
            raise MapOperationError("invalid_segment", "Выбранный сегмент отсутствует.", status=422)
        if route_length(points[index:index + 2]) < .01:
            raise MapOperationError("degenerate_segment", "Нельзя вставить муфту в вырожденный сегмент.", status=422)
        expected = segment_position(points[index], points[index + 1], data.fraction)
        requested = [data.position.longitude, data.position.latitude]
        # Only allow numeric rounding, never silently snap a forged off-line point.
        if route_length([expected, requested]) > .05:
            raise MapOperationError("off_route", "Точка не соответствует выбранному месту трассы.", status=422)
        position = [round(expected[0], 7), round(expected[1], 7)]
        left, right = points[:index + 1], points[index + 1:]
        # At a bend the vertex becomes the endpoint, not a duplicate vertex.
        if left[-1] == position:
            left = left[:-1]
        if right[0] == position:
            right = right[1:]
        first, second = [*left, position], [position, *right]
        if route_length(first) < 1 or route_length(second) < 1:
            raise MapOperationError("near_endpoint", "Муфта должна находиться не ближе 1 м по трассе от каждого конца.", status=422)
        marker = MapMarker(company_id=company_id, owner_user_id=current.owner_user_id,
            visibility=current.visibility, point_type="splice", building_link_role="none",
            latitude=position[1], longitude=position[0], **data.marker.model_dump())
        session.add(marker)
        await session.flush()
        tail = MapConnection(company_id=company_id, **{key: getattr(current, key) for key in (
            "owner_user_id", "visibility", "name", "description", "medium", "status", "fiber_count", "category",
            "target_building_id", "target_marker_id",
        )}, source_marker_id=marker.id, vertices=second[1:-1])
        current.target_building_id = None
        current.target_marker_id = marker.id
        current.vertices = first[1:-1]
        current.version += 1
        session.add(tail)
        await session.flush()
        # Build responses before the only commit, still holding every lock.
        result = MapConnectionSplitResponse(
            marker=await get_marker(session, company_id=company_id, user_id=user_id, can_manage=can_manage, marker_id=marker.id),
            connections=tuple([await get_connection(session, company_id=company_id, user_id=user_id, can_manage=can_manage, connection_id=i) for i in (current.id, tail.id)]),
        )
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


async def search_endpoints(session, *, company_id, user_id, query, limit, offset):
    buildings = _building_record_select().subquery()
    houses = select(literal("building").label("kind"), buildings.c.id, buildings.c.full_address.label("name"), buildings.c.latitude, buildings.c.longitude)
    markers = select(literal("marker").label("kind"), MapMarker.id, MapMarker.name, MapMarker.latitude, MapMarker.longitude).where(
        *visible_to(MapMarker, company_id, user_id), MapMarker.building_link_role != "represents"
    )
    rows = union_all(houses, markers).subquery()
    tokens = query.lower().replace("ё", "е").split()[:12]
    name = func.replace(func.lower(rows.c.name), "ё", "е")
    statement = select(rows).where(*(name.contains(token, autoescape=True) for token in tokens)).order_by(rows.c.name, rows.c.kind, rows.c.id).limit(limit + 1).offset(offset)
    result = (await session.execute(statement)).mappings().all()
    return {"items": [EndpointResponse(**row) for row in result[:limit]], "limit": limit, "offset": offset, "has_more": len(result) > limit}


async def list_presets(session, *, company_id, user_id):
    rows = (await session.scalars(select(MapMarkerStylePreset).where(
        MapMarkerStylePreset.company_id == company_id, MapMarkerStylePreset.owner_user_id == user_id
    ).order_by(MapMarkerStylePreset.name, MapMarkerStylePreset.id).limit(201))).all()
    if len(rows) > 200:
        raise MapOperationError("preset_limit", "Допускается не более 200 личных стилей.", status=422)
    return [MapStylePresetResponse.model_validate(row) for row in rows]


async def get_preset(session, *, company_id, user_id, preset_id):
    entity = await session.scalar(select(MapMarkerStylePreset).where(
        MapMarkerStylePreset.id == preset_id, MapMarkerStylePreset.company_id == company_id, MapMarkerStylePreset.owner_user_id == user_id
    ).with_for_update())
    if entity is None:
        raise MapOperationError("not_found", "Личный стиль не найден", status=404)
    return entity


async def save_preset(session, *, company_id, user_id, data, preset_id=None):
    try:
        await lock_map_company(session, company_id)
        entity = await get_preset(session, company_id=company_id, user_id=user_id, preset_id=preset_id) if preset_id else None
        if entity:
            check_version(entity, data.expected_version)
            entity.name, entity.appearance = data.name, data.appearance.model_dump()
            entity.version += 1
        else:
            count = await session.scalar(select(func.count()).select_from(MapMarkerStylePreset).where(MapMarkerStylePreset.company_id == company_id, MapMarkerStylePreset.owner_user_id == user_id))
            if count >= 200:
                raise MapOperationError("preset_limit", "Допускается не более 200 личных стилей.", status=422)
            entity = MapMarkerStylePreset(company_id=company_id, owner_user_id=user_id, name=data.name, appearance=data.appearance.model_dump())
            session.add(entity)
        await session.commit()
        await session.refresh(entity)
        return MapStylePresetResponse.model_validate(entity)
    except Exception:
        await session.rollback()
        raise


async def delete_preset(session, *, company_id, user_id, preset_id):
    entity = await get_preset(session, company_id=company_id, user_id=user_id, preset_id=preset_id)
    await session.delete(entity)
    await session.commit()
