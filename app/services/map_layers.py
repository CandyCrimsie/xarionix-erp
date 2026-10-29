"""Small bounded layer definitions; entity matching remains entirely in SQL."""
from sqlalchemy import and_, delete, exists, false, func, or_, select, true, update
from sqlalchemy.exc import IntegrityError

from core.map_domain import MapOperationError, check_version, lock_map_company, visible_to
from models.address_objects import AddressObject
from models.buildings import Building
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from models.map_workspace import MapLayer, MapLayerMember
from schemas.map_workspace import LayerResponse, LayerRules, MapFilter

MAX_LAYERS = 200
MAX_DEPTH = 8


async def get_target(session, target, *, company_id, user_id, lock=False):
    model = {"building": Building, "marker": MapMarker, "connection": MapConnection}[target.kind]
    query = select(model).where(model.id == target.id)
    if model is not Building:
        query = query.where(*visible_to(model, company_id, user_id))
    if lock:
        query = query.with_for_update()
    entity = await session.scalar(query.execution_options(populate_existing=True))
    if entity is None:
        raise MapOperationError("not_found", "Объект не найден или недоступен", status=404)
    return entity


async def list_layers(session, *, company_id):
    result = (await session.scalars(select(MapLayer).where(MapLayer.company_id == company_id)
        .order_by(MapLayer.sort_order, MapLayer.id).limit(MAX_LAYERS + 1))).all()
    if len(result) > MAX_LAYERS:
        raise MapOperationError("too_many_layers", "Слишком много слоёв компании. Обратитесь к администратору.", status=422)
    return result


async def save_layer(session, *, company_id, data, layer_id=None):
    try:
        await lock_map_company(session, company_id)
        layers = await list_layers(session, company_id=company_id)
        by_id = {layer.id: layer for layer in layers}
        current = by_id.get(layer_id)
        if layer_id is not None and current is None:
            raise MapOperationError("not_found", "Слой не найден", status=404)
        if current:
            check_version(current, data.expected_version)
            if current.mode != data.mode:
                raise MapOperationError("layer_mode_fixed", "Режим существующего слоя не меняется. Создайте новый слой; объекты копировать не нужно.")
        elif len(layers) >= MAX_LAYERS:
            raise MapOperationError("too_many_layers", f"Допускается до {MAX_LAYERS} слоёв компании", status=422)
        if data.parent_id is not None:
            parent = by_id.get(data.parent_id)
            if parent is None:
                raise MapOperationError("not_found", "Родительская группа недоступна", status=404)
            if parent.mode != "group":
                raise MapOperationError("not_a_group", "Родителем может быть только группа", status=422)
        # Validate the whole proposed tree, including descendants after a move.
        parents = {layer.id: layer.parent_id for layer in layers}
        parents[layer_id if current else -1] = data.parent_id
        for start in parents:
            seen, cursor = set(), start
            while cursor is not None:
                if cursor in seen or len(seen) >= MAX_DEPTH:
                    raise MapOperationError("layer_cycle", "Цикл или слишком большая глубина групп (максимум 8)", status=422)
                seen.add(cursor)
                cursor = parents.get(cursor)
        if data.rules.address_object_id is not None and await session.get(AddressObject, data.rules.address_object_id) is None:
            raise MapOperationError("not_found", "Адресный объект не найден", status=404)
        values = data.model_dump(exclude={"expected_version"})
        if current:
            for key, value in values.items():
                setattr(current, key, value)
            current.version += 1
        else:
            current = MapLayer(company_id=company_id, **values)
            session.add(current)
        await session.flush()
        result = LayerResponse.model_validate(current)
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


async def delete_layer(session, *, company_id, layer_id, expected_version):
    try:
        await lock_map_company(session, company_id)
        layer = await session.scalar(select(MapLayer).where(MapLayer.company_id == company_id, MapLayer.id == layer_id).with_for_update())
        if layer is None:
            raise MapOperationError("not_found", "Слой не найден", status=404)
        check_version(layer, expected_version)
        # Delete organisation only. Children survive under their grandparent.
        await session.execute(update(MapLayer).where(MapLayer.company_id == company_id, MapLayer.parent_id == layer.id)
            .values(parent_id=layer.parent_id, version=MapLayer.version + 1))
        await session.delete(layer)
        await session.commit()
    except Exception:
        await session.rollback()
        raise


async def move_layer(session, *, company_id, layer_id, data):
    """One sibling step even when every legacy sort_order is zero; atomic."""
    try:
        await lock_map_company(session, company_id)
        layers = await list_layers(session, company_id=company_id)
        current = next((layer for layer in layers if layer.id == layer_id), None)
        if current is None:
            raise MapOperationError("not_found", "Слой не найден", status=404)
        check_version(current, data.expected_version)
        siblings = sorted((layer for layer in layers if layer.parent_id == current.parent_id), key=lambda layer: (layer.sort_order, layer.id))
        index = siblings.index(current)
        target = index + data.direction
        if 0 <= target < len(siblings):
            siblings[index], siblings[target] = siblings[target], siblings[index]
            for order, layer in enumerate(siblings):
                if layer is current or layer.sort_order != order * 10:
                    layer.sort_order = order * 10
                    layer.version += 1
            await session.flush()
        result = [LayerResponse.model_validate(layer) for layer in sorted(layers, key=lambda layer: (layer.sort_order, layer.id))]
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise


async def canonical_target(session, target, *, company_id, user_id):
    from schemas.map_workspace import MapTarget
    entity = await get_target(session, target, company_id=company_id, user_id=user_id)
    # Represents is the visual style of the house, not an independent layer item.
    if target.kind == "marker" and entity.building_link_role == "represents":
        return MapTarget(kind="building", id=entity.building_id)
    return target


async def set_membership(session, *, company_id, user_id, layer_id, data):
    try:
        await lock_map_company(session, company_id)
        layer = await session.scalar(select(MapLayer).where(MapLayer.company_id == company_id, MapLayer.id == layer_id).with_for_update())
        if layer is None:
            raise MapOperationError("not_found", "Слой не найден", status=404)
        check_version(layer, data.expected_version)
        if layer.mode != "manual":
            raise MapOperationError("not_manual_layer", "Членства редактируются только у ручных слоёв", status=422)
        target = await canonical_target(session, data.target, company_id=company_id, user_id=user_id)
        field = getattr(MapLayerMember, target.kind + "_id")
        query = select(MapLayerMember).where(MapLayerMember.company_id == company_id, MapLayerMember.layer_id == layer_id, field == target.id)
        existing = await session.scalar(query)
        if data.present and not existing:
            session.add(MapLayerMember(company_id=company_id, layer_id=layer_id, **{target.kind + "_id": target.id}))
        elif not data.present and existing:
            await session.delete(existing)
        layer.version += 1
        await session.flush()
        result = LayerResponse.model_validate(layer)
        await session.commit()
        return result
    except IntegrityError as exc:
        await session.rollback()
        raise MapOperationError("membership_changed", "Объект или слой изменён. Обновите данные.") from exc
    except Exception:
        await session.rollback()
        raise


def _point_type_predicate(kind, entity, values):
    if not values:
        return true()
    if kind == "building":
        return true() if "building" in values else false()
    if kind == "marker":
        return entity.point_type.in_(values)
    endpoints = exists(select(MapMarker.id).where(MapMarker.id.in_([entity.source_marker_id, entity.target_marker_id]), MapMarker.point_type.in_(values)).correlate(entity))
    return or_(endpoints, or_(entity.source_building_id.is_not(None), entity.target_building_id.is_not(None)) if "building" in values else false())


def layer_predicate(layer, kind, entity, company_id):
    if layer.mode == "manual":
        field = getattr(MapLayerMember, kind + "_id")
        target = field == entity.id
        if kind == "marker":
            target = or_(and_(entity.building_link_role == "represents", MapLayerMember.building_id == entity.building_id),
                         and_(entity.building_link_role != "represents", field == entity.id))
        return exists(select(MapLayerMember.id).where(MapLayerMember.company_id == company_id,
            MapLayerMember.layer_id == layer.id, target).correlate(entity))
    rules = LayerRules.model_validate(layer.rules)
    if kind != "connection" and (rules.media or rules.statuses):
        return false()  # Cable-only rules must not accidentally match every point.
    terms = [_point_type_predicate(kind, entity, rules.point_types)]
    if rules.address_object_id is not None:
        tree = select(AddressObject.id).where(AddressObject.id == rules.address_object_id).cte(f"layer_address_{layer.id}", recursive=True)
        tree = tree.union(select(AddressObject.id).join(tree, AddressObject.parent_id == tree.c.id))
        address_ids = select(tree.c.id)
        if kind == "building":
            terms.append(entity.address_object_id.in_(address_ids))
        else:
            if kind == "marker":
                building_ids = Building.id == entity.building_id
            else:
                marker_buildings = select(MapMarker.building_id).where(MapMarker.id.in_([entity.source_marker_id, entity.target_marker_id])).correlate(entity)
                building_ids = or_(Building.id == entity.source_building_id, Building.id == entity.target_building_id, Building.id.in_(marker_buildings))
            terms.append(exists(select(Building.id).where(building_ids, Building.address_object_id.in_(address_ids)).correlate(entity)))
    if kind == "connection":
        if rules.media:
            terms.append(entity.medium.in_(rules.media))
        if rules.statuses:
            terms.append(entity.status.in_(rules.statuses))
    return and_(*terms)


async def map_predicates(session, *, company_id, kind, filters: MapFilter | None):
    if filters is None:
        return []
    entity = {"building": Building, "marker": MapMarker, "connection": MapConnection}[kind]
    terms = [false() if filters.point_types_enabled and not filters.point_types else _point_type_predicate(kind, entity, filters.point_types)]
    if kind == "connection":
        if filters.medium != "all":
            terms.append(entity.medium == filters.medium)
        if filters.status != "all":
            terms.append(entity.status == filters.status)
        if filters.installation != "all":
            terms.append(or_(entity.installation_methods.contains([filters.installation]),
                entity.installation_methods == [] if filters.installation == "unknown" else false()))
    if not filters.layers_active:
        return terms
    layers = await list_layers(session, company_id=company_id)
    selected = set(filters.layer_ids)
    # Defensive expansion also makes direct API group selection predictable.
    for _ in range(MAX_DEPTH):
        selected.update(layer.id for layer in layers if layer.parent_id in selected)
    matches = {layer.id: layer_predicate(layer, kind, entity, company_id) for layer in layers if layer.mode != "group"}
    included = [predicate for id_, predicate in matches.items() if id_ in selected]
    if filters.include_unassigned:
        included.append(~or_(*matches.values()) if matches else true())
    terms.append(or_(*included) if included else false())
    return terms


async def target_layers(session, *, company_id, user_id, target):
    target = await canonical_target(session, target, company_id=company_id, user_id=user_id)
    entity = {"building": Building, "marker": MapMarker, "connection": MapConnection}[target.kind]
    layers = await list_layers(session, company_id=company_id)
    # One SQL statement for all layer predicates, not one query per layer.
    from sqlalchemy import literal, union_all
    statements = [select(literal(layer.id).label("layer_id")).select_from(entity).where(entity.id == target.id,
        layer_predicate(layer, target.kind, entity, company_id)) for layer in layers if layer.mode != "group"]
    found = set((await session.scalars(union_all(*statements))).all()) if statements else set()
    return [LayerResponse.model_validate(layer) for layer in layers if layer.id in found]


async def inherit_route_layers(session, *, company_id, connection_id, marker_id, tail_id=None):
    """Called inside split/place's transaction; no commits or permission widening."""
    ids = list((await session.scalars(select(MapLayerMember.layer_id).where(
        MapLayerMember.company_id == company_id, MapLayerMember.connection_id == connection_id))).all())
    for layer_id in ids:
        session.add(MapLayerMember(company_id=company_id, layer_id=layer_id, marker_id=marker_id))
        if tail_id is not None:
            session.add(MapLayerMember(company_id=company_id, layer_id=layer_id, connection_id=tail_id))
    if ids:
        await session.execute(update(MapLayer).where(MapLayer.company_id == company_id, MapLayer.id.in_(ids)).values(version=MapLayer.version + 1))
    await session.flush()
