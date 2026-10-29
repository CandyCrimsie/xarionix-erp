"""On-demand metadata. Derived address/coordinates/cable properties stay canonical."""
from sqlalchemy import select

from core.map_domain import MapOperationError, check_version, lock_map_company, require_write
from models.map_workspace import MapPassport
from models.company import Company
from repositories.addresses import get_building_record
from schemas.map_workspace import PassportData
from services.map_layers import get_target, target_layers


def _spec_kind(kind, entity):
    if kind == "building":
        return "building"
    if kind == "marker" and entity.point_type in {"pole", "cabinet"}:
        return entity.point_type
    return "general"


async def get_passport(session, *, company_id, user_id, can_manage, target):
    entity = await get_target(session, target, company_id=company_id, user_id=user_id)
    record = await session.scalar(select(MapPassport).where(MapPassport.company_id == company_id,
        getattr(MapPassport, target.kind + "_id") == target.id))
    data = PassportData.model_validate(record.data) if record else PassportData(specs={"kind": _spec_kind(target.kind, entity)})
    if data.specs.kind != _spec_kind(target.kind, entity):
        # A deliberate marker-type change never silently migrates incompatible
        # data. Preserve it in DB and require an explicit reviewed save.
        specs_notice = "Тип объекта изменён. Уточните характеристики перед сохранением паспорта."
    else:
        specs_notice = None
    info = {"kind": target.kind, "id": target.id, "name": None, "description": None,
        "version": None, "point_type": "building", "status": None, "latitude": None, "longitude": None}
    info["company_name"] = await session.scalar(select(Company.name).where(Company.id == company_id))
    if target.kind == "building":
        building = await get_building_record(session, target.id)
        info.update(name=building.full_address, full_address=building.full_address,
            latitude=float(entity.latitude) if entity.latitude is not None else None,
            longitude=float(entity.longitude) if entity.longitude is not None else None)
    elif target.kind == "marker":
        from services.map_markers import get_marker
        marker = await get_marker(session, company_id=company_id, user_id=user_id, can_manage=can_manage, marker_id=target.id)
        info.update({key: getattr(marker, key) for key in ("name", "description", "version", "point_type", "latitude", "longitude", "building_id", "building_link_role", "building_full_address")})
    else:
        from services.map_connections import get_connection
        line = await get_connection(session, company_id=company_id, user_id=user_id, can_manage=can_manage, connection_id=target.id)
        info.update({key: getattr(line, key) for key in ("name", "description", "version", "status", "medium", "fiber_count", "category", "length_m", "installation_methods")})
        info.update(point_type="connection", source=line.source.model_dump(), target=line.target.model_dump())
    return {"entity": info, "version": record.version if record else 0, "data": data.model_dump(mode="json"),
        "can_manage": can_manage if target.kind == "building" or entity.visibility == "company" else entity.owner_user_id == user_id,
        "layers": await target_layers(session, company_id=company_id, user_id=user_id, target=target), "notice": specs_notice}


async def save_passport(session, *, company_id, user_id, can_manage, target, data):
    try:
        await lock_map_company(session, company_id)
        entity = await get_target(session, target, company_id=company_id, user_id=user_id, lock=True)
        if target.kind == "building":
            if not can_manage:
                raise MapOperationError("permission_denied", "Нет права изменять паспорт дома", status=403)
            if data.name is not None or data.description is not None or data.status is not None:
                raise MapOperationError("derived_field", "Адрес дома редактируется в адресном каталоге", status=422)
        else:
            require_write(entity, user_id, can_manage)
            if data.expected_entity_version is None:
                raise MapOperationError("version_required", "Нужна версия объекта", status=422)
            check_version(entity, data.expected_entity_version)
        if data.data.specs.kind != _spec_kind(target.kind, entity):
            raise MapOperationError("wrong_passport_type", "Характеристики не соответствуют типу объекта", status=422)
        if target.kind == "connection" and data.data.operational_status is not None:
            raise MapOperationError("duplicate_status", "Используйте существующий статус кабеля", status=422)
        if target.kind != "connection" and data.status is not None:
            raise MapOperationError("wrong_status_field", "Используйте состояние в паспорте объекта", status=422)
        record = await session.scalar(select(MapPassport).where(MapPassport.company_id == company_id,
            getattr(MapPassport, target.kind + "_id") == target.id).with_for_update().execution_options(populate_existing=True))
        if (record.version if record else 0) != data.expected_version:
            raise MapOperationError("stale_version", "Паспорт уже изменён. Перечитайте его перед сохранением.")
        if record is None:
            record = MapPassport(company_id=company_id, **{target.kind + "_id": target.id}, version=1)
            session.add(record)
        else:
            record.version += 1
        record.data = data.data.model_dump(mode="json")
        if target.kind != "building":
            if data.name is not None:
                entity.name = data.name
            if "description" in data.model_fields_set:
                entity.description = data.description
            if target.kind == "connection" and data.status is not None:
                entity.status = data.status
            entity.version += 1
        await session.flush()
        result = await get_passport(session, company_id=company_id, user_id=user_id, can_manage=can_manage, target=target)
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise
