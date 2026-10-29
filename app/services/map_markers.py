import hashlib
import hmac
import json

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import config
from core.map_domain import MapOperationError, check_version, lock_map_company, require_write, visible_to
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from repositories.addresses import get_building_record
from repositories.map_markers import get_map_marker, list_map_markers, marker_records_query
from schemas.map_markers import MapMarkerCreate, MapMarkerResponse, MapMarkerUpdate, MarkerBindingEffect
from services.building_coordinates import lock_buildings, set_building_position
from services.map_route_objects import guard_endpoint_position, marker_attachments


class MapMarkerNotFoundError(Exception):
    pass


class MapMarkerBuildingNotFoundError(Exception):
    pass


class MapMarkerSyncConflictError(Exception):
    pass


def marker_response(row, *, user_id: int, can_manage: bool) -> MapMarkerResponse:
    marker, building, full_address = row
    result = MapMarkerResponse.model_validate(marker)
    if marker.building_link_role == "represents":
        result.latitude = float(building.latitude) if building and building.latitude is not None else None
        result.longitude = float(building.longitude) if building and building.longitude is not None else None
    result.building_full_address = full_address if building else None
    result.can_manage = marker.owner_user_id == user_id if marker.visibility == "private" else can_manage
    return result


async def get_markers(session, *, company_id, user_id, can_manage=False, filters=None, **bounds):
    from services.map_layers import map_predicates
    rows = await list_map_markers(session, company_id=company_id, user_id=user_id, **bounds,
        predicates=await map_predicates(session, company_id=company_id, kind="marker", filters=filters))
    if len(rows) > 5000:
        raise MapOperationError("viewport_too_large", "Слишком много меток. Увеличьте масштаб.", status=422)
    result = [marker_response(row, user_id=user_id, can_manage=can_manage) for row in rows]
    links = await marker_attachments(session, [marker.id for marker in result])
    for marker in result:
        marker.route_attachment = links.get(marker.id)
    return result


async def get_marker(session, *, company_id, marker_id, user_id, can_manage=False):
    row = (await session.execute(marker_records_query().where(
        MapMarker.id == marker_id, *visible_to(MapMarker, company_id, user_id)
    ).execution_options(populate_existing=True))).one_or_none()
    if row is None:
        raise MapMarkerNotFoundError
    result = marker_response(row, user_id=user_id, can_manage=can_manage)
    result.route_attachment = (await marker_attachments(session, [result.id])).get(result.id)
    return result


def _position(building):
    return {"latitude": float(building.latitude) if building.latitude is not None else None, "longitude": float(building.longitude) if building.longitude is not None else None, "updated_at": str(building.updated_at)} if building else None


async def _binding_snapshot(session, *, marker, target, occupant, values):
    async def house_info(building_id):
        record = await get_building_record(session, building_id) if building_id else None
        return {"id": building_id, "address": record.full_address, "position": _position(record.building)} if record else None
    snapshot = {
        "marker": {"id": marker.id, "version": marker.version, "name": marker.name, "building_id": marker.building_id} if marker else None,
        "previous_building": await house_info(marker.building_id) if marker and marker.building_id is not None else None,
        "target_building": await house_info(target.id),
        "previous_marker": {"id": occupant.id, "version": occupant.version, "name": occupant.name} if occupant else None,
        "requested_name": values["name"],
        "requested_position": values.get("building_position"),
    }
    operation = {key: value for key, value in values.items() if key not in {"binding_confirmation", "expected_version"}}
    secret = config.JWT_SECRET
    if hasattr(secret, "get_secret_value"):
        secret = secret.get_secret_value()
    token = hmac.new(str(secret).encode(), json.dumps([snapshot, operation], sort_keys=True, default=str).encode(), hashlib.sha256).hexdigest()
    return snapshot, token


async def _save_marker(session: AsyncSession, *, company_id, user_id, can_manage, data, marker_id=None):
    try:
        binding_effects = []
        await lock_map_company(session, company_id)
        marker = await get_map_marker(session, company_id=company_id, marker_id=marker_id, user_id=user_id) if marker_id else None
        if marker_id and marker is None:
            raise MapMarkerNotFoundError
        if marker:
            require_write(marker, user_id, can_manage)
            check_version(marker, data.expected_version)
        changes = data.model_dump(exclude_unset=True) if marker else data.model_dump()
        if changes.get("sync_building_coordinates"):
            raise MapOperationError("legacy_coordinate_sync_removed", "Выберите роль связи с домом. Для изменения его точки используйте «Изменить расположение дома».", status=422)
        values = {column.name: getattr(marker, column.name) for column in MapMarker.__table__.columns} if marker else {}
        values.update(changes)
        building_id = values.get("building_id")
        # Compatibility: a bare old building_id is always informational.
        link = values.get("building_link_role")
        if link is None or ("building_id" in changes and "building_link_role" not in changes):
            link = "reference" if building_id is not None else "none"
        visibility = values.get("visibility") or ("private" if values["point_type"] == "note" else "company")
        if not can_manage and (visibility != "private" or values["point_type"] != "note"):
            raise MapOperationError("permission_denied", "Недостаточно прав для общего или технического объекта", status=403)
        if link == "represents" and (visibility != "company" or values["point_type"] != "building"):
            raise MapOperationError("invalid_building_link", "Основная метка дома должна быть общим объектом типа «Дом».", status=422)
        if (link == "none") != (building_id is None):
            raise MapOperationError("invalid_building_link", "Выберите дом и роль его связи либо снимите привязку.", status=422)
        buildings = await lock_buildings(session, {id_ for id_ in [building_id, marker.building_id if marker else None] if id_ is not None})
        building = buildings.get(building_id)
        if building_id is not None and building is None:
            raise MapMarkerBuildingNotFoundError
        if marker:
            await session.refresh(marker, with_for_update=True)
            link_info = (await marker_attachments(session, [marker.id])).get(marker.id)
            fixed_fields = {"latitude", "longitude", "point_type", "visibility", "building_id", "building_link_role"}
            def changed_fixed_field(key):
                if key not in changes:
                    return False
                value, previous = changes[key], getattr(marker, key)
                if key in {"latitude", "longitude"} and value is not None and previous is not None:
                    return round(float(value), 7) != round(float(previous), 7)
                return value != previous
            if link_info and any(changed_fixed_field(key) for key in fixed_fields):
                raise MapOperationError("marker_is_route_object", "Объект закреплён на трассе. Сначала явно отвяжите его, чтобы изменить положение или тип.")
            if {"latitude", "longitude"} & changes.keys():
                await guard_endpoint_position(session, "marker", marker.id, values.get("latitude"), values.get("longitude"))
        if marker and marker.visibility != visibility:
            dependent = await session.scalar(select(MapConnection.id).where(or_(
                MapConnection.source_marker_id == marker.id, MapConnection.target_marker_id == marker.id
            )).limit(1))
            if dependent:
                raise MapOperationError("visibility_has_connections", "Перед изменением видимости удалите или переназначьте соединения.")
        if values.get("building_position") and (link != "represents" or not can_manage):
            raise MapOperationError("permission_denied", "Изменить расположение общего дома можно только с правом управления адресами.", status=403)
        rebinding = marker and marker.building_id is not None and building_id is not None and marker.building_id != building_id
        if link == "represents":
            if marker and marker.building_link_role != "represents" and await session.scalar(
                select(MapConnection.id).where(or_(MapConnection.source_marker_id == marker.id, MapConnection.target_marker_id == marker.id)).limit(1)
            ):
                raise MapOperationError("endpoint_has_connections", "Сначала переназначьте линии самостоятельного объекта. Изменение оформления не переподключает их к дому.")
            occupant = await session.scalar(select(MapMarker).where(
                MapMarker.company_id == company_id, MapMarker.building_id == building_id,
                MapMarker.building_link_role == "represents",
                MapMarker.id != marker_id if marker_id else True,
            ).with_for_update())
            moving = rebinding
            if occupant or moving:
                snapshot, token = await _binding_snapshot(session, marker=marker, target=building, occupant=occupant, values=values)
                if not hmac.compare_digest(changes.get("binding_confirmation") or "", token):
                    raise MapOperationError("building_binding_conflict", "Подтвердите перепривязку дома.", snapshot=snapshot, confirmation_token=token)
            if occupant:
                occupant.latitude, occupant.longitude = building.latitude, building.longitude
                occupant.building_link_role = "reference"
                occupant.version += 1
                binding_effects.append(MarkerBindingEffect(id=occupant.id, building_id=occupant.building_id,
                    building_link_role=occupant.building_link_role, latitude=occupant.latitude,
                    longitude=occupant.longitude, version=occupant.version))
                await session.flush()
            if values.get("building_position"):
                await set_building_position(session, building, **values["building_position"])
            values["latitude"] = values["longitude"] = None
        else:
            if rebinding:
                snapshot, token = await _binding_snapshot(session, marker=marker, target=building, occupant=None, values=values)
                if not hmac.compare_digest(changes.get("binding_confirmation") or "", token):
                    raise MapOperationError("building_binding_conflict", "Подтвердите старую и новую адресную связь.", snapshot=snapshot, confirmation_token=token)
            if marker and marker.building_link_role == "represents":
                old = buildings.get(marker.building_id)
                if "latitude" not in changes and old:
                    values["latitude"], values["longitude"] = old.latitude, old.longitude
            if (values.get("latitude") is None) != (values.get("longitude") is None):
                raise MapOperationError("invalid_position", "Укажите широту и долготу вместе.", status=422)
            if not marker and values.get("latitude") is None:
                raise MapOperationError("missing_position", "Выберите точку на карте.", status=422)
        values.update(visibility=visibility, building_link_role=link, owner_user_id=user_id if visibility == "private" else None, sync_building_coordinates=False)
        fields = set(MapMarker.__table__.columns.keys()) - {"id", "company_id", "created_at", "updated_at", "version"}
        if marker:
            for name in fields:
                if name in values:
                    setattr(marker, name, values[name])
            marker.version += 1
        else:
            marker = MapMarker(company_id=company_id, **{name: value for name, value in values.items() if name in fields})
            session.add(marker)
        await session.flush()
        saved_id = marker.id
        await session.commit()
        result = await get_marker(session, company_id=company_id, marker_id=saved_id, user_id=user_id, can_manage=can_manage)
        result.binding_effects = binding_effects
        return result
    except IntegrityError as exc:
        await session.rollback()
        raise MapOperationError("building_binding_conflict", "Привязка изменилась. Повторите сохранение и подтвердите актуальные связи.") from exc
    except Exception:
        await session.rollback()
        raise


async def create_marker(session, *, company_id, user_id, can_manage, data: MapMarkerCreate):
    return await _save_marker(session, company_id=company_id, user_id=user_id, can_manage=can_manage, data=data)


async def update_marker(session, *, company_id, user_id, can_manage, marker_id, data: MapMarkerUpdate):
    return await _save_marker(session, company_id=company_id, user_id=user_id, can_manage=can_manage, marker_id=marker_id, data=data)


async def delete_marker(session, *, company_id, marker_id, user_id, can_manage, expected_version=None):
    try:
        await lock_map_company(session, company_id)
        marker = await get_map_marker(session, company_id=company_id, marker_id=marker_id, user_id=user_id)
        if marker is None:
            raise MapMarkerNotFoundError
        await session.refresh(marker, with_for_update=True)
        require_write(marker, user_id, can_manage)
        check_version(marker, expected_version)
        dependency = await session.scalar(select(MapConnection.id).where(or_(
            MapConnection.source_marker_id == marker_id, MapConnection.target_marker_id == marker_id
        )).limit(1))
        if dependency:
            from services.address_dependencies import deletion_dependencies
            detail = await deletion_dependencies(session, "marker", marker_id, company_id=company_id, user_id=user_id)
            # Keep the established code/legacy examples, add the shared dialog contract.
            examples = next((group["items"] for group in detail["dependencies"] if group["type"] == "map_connection"), [])
            raise MapOperationError("endpoint_has_connections", detail["message"], object=detail["object"],
                dependencies=detail["dependencies"], connections=examples)
        await session.delete(marker)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
