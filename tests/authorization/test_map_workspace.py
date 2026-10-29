"""Workspace regressions: real SQL, HTTP authorization, no Python matching mocks."""
import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.map_domain import MapOperationError
from database.map_workspace_upgrade import upgrade_workspace_schema
from models.buildings import Building
from models.company import Company
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from models.map_workspace import MapLayer, MapLayerMember, MapPassport, MapPreference
from schemas.map_workspace import LayerCreate, PassportWrite, MapTarget, PreferenceWrite
from services.map_passports import save_passport
from services.map_preferences import save_preferences
from test_map_api import marker_building_context, primary_marker, represents_payload
from test_map_graph_api import cable, point, reader
from test_map_api import create_building
from test_map_connection_split import route_context, split_payload

pytestmark = pytest.mark.usefixtures("clean_test_redis")


async def layer(client, headers, **values):
    response = await client.post("/api/v1/map/layers", headers=headers, json={"name": "Участок", **values})
    assert response.status_code == 201, response.text
    return response.json()


async def member(client, headers, item, kind, id_, present=True):
    response = await client.put(f"/api/v1/map/layers/{item['id']}/members", headers=headers,
        json={"expected_version": item["version"], "present": present, "target": {"kind": kind, "id": id_}})
    assert response.status_code == 200, response.text
    return response.json()


def selected(*layers, unassigned=False, **filters):
    return {"layers_active": "true", "include_unassigned": str(unassigned).lower(), "layer_ids": [item["id"] for item in layers], **filters}


@pytest.mark.asyncio
async def test_layer_tree_crud_cycles_and_safe_group_deletion(db_session, api_client):
    company, _, headers, _ = await marker_building_context(db_session, api_client)
    parent = await layer(api_client, headers, name="Город", mode="group")
    child = await layer(api_client, headers, name="Проект", mode="group", parent_id=parent["id"])
    leaf = await layer(api_client, headers, parent_id=child["id"])
    invalid = await api_client.patch(f"/api/v1/map/layers/{parent['id']}", headers=headers,
        json={**{key: parent[key] for key in ("name", "mode", "rules", "sort_order")}, "parent_id": child["id"], "expected_version": 1})
    assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "layer_cycle"
    result = await api_client.patch(f"/api/v1/map/layers/{leaf['id']}", headers=headers,
        json={"name": "Улица — проект", "mode": "manual", "parent_id": child["id"], "sort_order": -10, "expected_version": 1})
    assert result.status_code == 200 and result.json()["version"] == 2
    assert (await api_client.delete(f"/api/v1/map/layers/{child['id']}", headers=headers, params={"expected_version": 1})).status_code == 204
    rows = (await api_client.get("/api/v1/map/layers", headers=headers)).json()
    assert next(row for row in rows if row["id"] == leaf["id"])["parent_id"] == parent["id"]
    assert await db_session.scalar(select(func.count()).select_from(MapLayer).where(MapLayer.company_id == company)) == 2


@pytest.mark.asyncio
async def test_layer_move_is_one_atomic_step_even_with_equal_orders(db_session, api_client):
    _, _, headers, _ = await marker_building_context(db_session, api_client)
    a, b, c = await layer(api_client, headers, name="A"), await layer(api_client, headers, name="B"), await layer(api_client, headers, name="C")
    url = f"/api/v1/map/layers/{c['id']}/move"
    result = await api_client.post(url, headers=headers, json={"direction": -1, "expected_version": 1})
    assert result.status_code == 200, result.text
    assert [item["id"] for item in result.json()] == [a["id"], c["id"], b["id"]]
    stale = await api_client.post(url, headers=headers, json={"direction": 1, "expected_version": 1})
    assert stale.status_code == 409
    assert [item["id"] for item in (await api_client.get("/api/v1/map/layers", headers=headers)).json()] == [a["id"], c["id"], b["id"]]


@pytest.mark.asyncio
async def test_manual_layers_or_unassigned_and_no_duplicate_entities(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await point(api_client, headers, point_type="cabinet", visibility="company")
    other = await point(api_client, headers, point_type="pole", visibility="company", latitude=55.6)
    a, b = await layer(api_client, headers, name="A"), await layer(api_client, headers, name="B")
    a = await member(api_client, headers, a, "marker", marker["id"])
    b = await member(api_client, headers, b, "marker", marker["id"])
    for params in (selected(a, b), selected(b)):
        response = await api_client.get("/api/v1/map/markers", headers=headers, params=params)
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()] == [marker["id"]]
    assert (await api_client.get("/api/v1/map/markers", headers=headers, params=selected())).json() == []
    assert [m["id"] for m in (await api_client.get("/api/v1/map/markers", headers=headers, params=selected(unassigned=True))).json()] == [other["id"]]
    assert (await api_client.delete(f"/api/v1/map/layers/{a['id']}", headers=headers, params={"expected_version": a["version"]})).status_code == 204
    assert await db_session.get(MapMarker, marker["id"]) is not None
    assert len((await api_client.get("/api/v1/map/markers", headers=headers, params=selected(b))).json()) == 1


@pytest.mark.asyncio
async def test_dynamic_address_and_cable_rules_are_sql_and_intersect_filters(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    linked = await point(api_client, headers, point_type="cabinet", visibility="company", building_id=building["id"])
    end = await point(api_client, headers, point_type="pole", visibility="company", latitude=55.7)
    route = await api_client.post("/api/v1/map/connections", headers=headers, json=cable(
        {"kind": "marker", "id": linked["id"]}, {"kind": "marker", "id": end["id"]}, installation_methods=["duct"]))
    assert route.status_code == 201, route.text
    address = await layer(api_client, headers, mode="dynamic", rules={"address_object_id": building["address_object_id"]})
    response = await api_client.get("/api/v1/map/markers", headers=headers, params=selected(address))
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [linked["id"]]
    assert len((await api_client.get("/api/v1/map/connections", headers=headers, params=selected(address))).json()) == 1
    fiber = await layer(api_client, headers, mode="dynamic", rules={"media": ["fiber"], "statuses": ["active"]})
    assert (await api_client.get("/api/v1/map/markers", headers=headers, params=selected(fiber))).json() == []
    assert (await api_client.get("/api/v1/map/connections", headers=headers, params=selected(fiber, medium="utp"))).json() == []
    assert len((await api_client.get("/api/v1/map/connections", headers=headers, params=selected(fiber, installation="duct"))).json()) == 1
    assert (await api_client.get("/api/v1/map/connections", headers=headers, params=selected(fiber, installation="aerial"))).json() == []
    assert (await api_client.patch(f"/api/v1/map/markers/{linked['id']}", headers=headers,
        json={"expected_version": linked["version"], "building_id": None, "building_link_role": "none"})).status_code == 200
    assert (await api_client.get("/api/v1/map/markers", headers=headers, params=selected(address))).json() == []


@pytest.mark.asyncio
async def test_primary_marker_uses_house_membership_and_house_is_not_lost(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    primary = await primary_marker(api_client, headers, building)
    item = await layer(api_client, headers)
    await member(api_client, headers, item, "marker", primary["id"])
    assert (await db_session.scalar(select(MapLayerMember))).building_id == building["id"]
    response = await api_client.get("/api/v1/map/markers", headers=headers, params=selected(item))
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [primary["id"]]
    params = {**selected(item), "west": 30, "east": 40, "south": 50, "north": 60}
    response = await api_client.get("/api/v1/map/buildings", headers=headers, params=params)
    assert response.status_code == 200, response.text
    assert [f["id"] for f in response.json()["features"]] == [building["id"]]


@pytest.mark.asyncio
async def test_layers_do_not_grant_access_to_private_or_foreign_targets(db_session, api_client):
    company, _, headers, _ = await marker_building_context(db_session, api_client)
    _, user_headers = await reader(db_session, api_client, company, "workspace-reader")
    private = await point(api_client, user_headers, point_type="note", visibility="private")
    item = await layer(api_client, headers)
    response = await api_client.put(f"/api/v1/map/layers/{item['id']}/members", headers=headers,
        json={"expected_version": 1, "present": True, "target": {"kind": "marker", "id": private["id"]}})
    assert response.status_code == 404
    for path in (f"/map/objects/marker/{private['id']}/layers", f"/map/passports/marker/{private['id']}", f"/map/objects/marker/{private['id']}/dependencies"):
        assert (await api_client.get("/api/v1" + path, headers=headers)).status_code == 404
    assert (await api_client.post("/api/v1/map/layers", headers=user_headers, json={"name": "Чужая структура"})).status_code == 403
    other_company = Company(name="Другой контекст", short_name="OTHER")
    db_session.add(other_company); await db_session.flush()
    foreign = MapLayer(company_id=other_company.id, name="Секретный слой", mode="manual")
    db_session.add(foreign); await db_session.commit()
    assert all(row["id"] != foreign.id for row in (await api_client.get("/api/v1/map/layers", headers=headers)).json())
    assert (await api_client.put(f"/api/v1/map/layers/{foreign.id}/members", headers=headers,
        json={"expected_version": 1, "present": True, "target": {"kind": "marker", "id": private["id"]}})).status_code == 404


@pytest.mark.asyncio
async def test_preferences_are_personal_versioned_and_deleted_layers_do_not_show_all(db_session, api_client):
    company, _, headers, _ = await marker_building_context(db_session, api_client)
    _, reader_headers = await reader(db_session, api_client, company, "preference-reader")
    item = await layer(api_client, headers)
    settings = {"visible_layer_ids": [item["id"]], "include_unassigned": False, "connection_mode": "hidden", "medium": "fiber"}
    result = await api_client.put("/api/v1/map/preferences", headers=headers, json={"expected_version": 0, "settings": settings})
    assert result.status_code == 200, result.text
    assert (await api_client.put("/api/v1/map/preferences", headers=headers, json={"expected_version": 0, "settings": {}})).status_code == 409
    assert (await api_client.get("/api/v1/map/preferences", headers=reader_headers)).json()["version"] == 0
    assert (await api_client.delete(f"/api/v1/map/layers/{item['id']}", headers=headers, params={"expected_version": 1})).status_code == 204
    result = (await api_client.get("/api/v1/map/preferences", headers=headers)).json()
    assert result["settings"]["visible_layer_ids"] == [] and result["settings"]["include_unassigned"] is False
    assert result["notice"]
    for bad in ({"schema_version": 2}, {"geometry": []}, {"visible_layer_ids": [-1]}, {"connection_mode": "all-company"}):
        assert (await api_client.put("/api/v1/map/preferences", headers=headers, json={"expected_version": 1, "settings": bad})).status_code == 422


@pytest.mark.asyncio
async def test_passports_keep_canonical_fields_versions_and_geometry_tokens(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await point(api_client, headers, point_type="cabinet", visibility="company")
    end = await point(api_client, headers, point_type="pole", visibility="company", latitude=55.7)
    line = (await api_client.post("/api/v1/map/connections", headers=headers, json=cable(
        {"kind": "marker", "id": marker["id"]}, {"kind": "marker", "id": end["id"]}, installation_methods=["duct"]))).json()
    for kind, entity, specs in (("building", building, {"kind": "building", "floors": 9, "premises": 0}),
                               ("marker", marker, {"kind": "cabinet", "height_u": 12}), ("connection", line, {"kind": "general"})):
        url = f"/api/v1/map/passports/{kind}/{entity['id']}"
        response = await api_client.get(url, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["version"] == 0
        data = {"expected_version": 0, "expected_entity_version": entity.get("version"), "data": {"inventory_number": "INV-1", "specs": specs}}
        if kind != "building": data.update(name="Новое имя", description="Текст паспорта")
        if kind == "connection": data["status"] = "construction"
        saved = await api_client.put(url, headers=headers, json=data)
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"]["inventory_number"] == "INV-1" and saved.json()["version"] == 1
        assert (await api_client.put(url, headers=headers, json=data)).status_code == 409
    updated = (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json()
    assert updated["geometry_token"] == line["geometry_token"]
    assert updated["status"] == "construction" and updated["installation_methods"] == ["duct"]
    assert (await api_client.get(f"/api/v1/map/markers/{marker['id']}", headers=headers)).json()["name"] == "Новое имя"
    assert await db_session.scalar(select(func.count()).select_from(MapMarker)) == 2


@pytest.mark.asyncio
async def test_passport_permissions_validation_and_private_ownership(db_session, api_client):
    company, _, headers, building = await marker_building_context(db_session, api_client)
    _, own = await reader(db_session, api_client, company, "passport-owner")
    marker = await point(api_client, own, point_type="note", visibility="private")
    payload = {"expected_version": 0, "expected_entity_version": 1, "data": {"specs": {"kind": "general"}, "note": "Личный текст"}}
    url = f"/api/v1/map/passports/marker/{marker['id']}"
    assert (await api_client.put(url, headers=own, json=payload)).status_code == 200
    assert (await api_client.get(url, headers=headers)).status_code == 404
    assert (await api_client.get(url)).status_code == 401
    house = f"/api/v1/map/passports/building/{building['id']}"
    assert (await api_client.put(house, headers=own, json={"expected_version": 0, "data": {"specs": {"kind": "building"}}})).status_code == 403
    for data in ({"note": "<svg onload=alert(1)>"}, {"specs": {"kind": "pole", "height_m": 0}}, {"specs": {"kind": "building", "floors": 0}}, {"latitude": 55}):
        response = await api_client.put(house, headers=headers, json={"expected_version": 0, "data": data})
        assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_metadata_migration_preserves_old_network_and_is_idempotent(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await point(api_client, headers, point_type="cabinet", visibility="company")
    await db_session.execute(text("DROP TABLE map_passports, map_preferences, map_layer_members, map_layers"))
    connection = await db_session.connection()
    report = await upgrade_workspace_schema(connection)
    assert report["upgrade_required"] is True
    assert (await upgrade_workspace_schema(connection))["upgrade_required"] is False
    assert await db_session.get(Building, building["id"]) is not None
    assert await db_session.get(MapMarker, marker["id"]) is not None
    assert await db_session.scalar(select(func.count()).select_from(MapLayer)) == 0


@pytest.mark.asyncio
async def test_parallel_preferences_and_passports_reject_stale_writers(db_session, api_client):
    company, _, headers, building = await marker_building_context(db_session, api_client)
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)
    async def attempt(index, operation):
        async with factory() as session:
            try:
                if operation == "preferences":
                    return await save_preferences(session, company_id=company, user_id=1, data=PreferenceWrite(expected_version=0, settings={"include_unassigned": bool(index)}))
                return await save_passport(session, company_id=company, user_id=1, can_manage=True, target=MapTarget(kind="building", id=building["id"]),
                    data=PassportWrite(expected_version=0, data={"note": str(index), "specs": {"kind": "building"}}))
            except MapOperationError as exc:
                return exc.detail["code"]
    for operation, code in (("preferences", "stale_preferences"), ("passport", "stale_version")):
        result = await asyncio.gather(attempt(1, operation), attempt(2, operation))
        assert result.count(code) == 1


@pytest.mark.asyncio
async def test_reference_rebinding_requires_the_exact_old_and_new_snapshot(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    second = await create_building(api_client, headers, parent_id=building["address_object_id"], number="55", latitude=None, longitude=None)
    marker = await point(api_client, headers, point_type="cabinet", visibility="company", building_id=building["id"])
    payload = {"expected_version": marker["version"], "building_id": second["id"], "building_link_role": "reference"}
    url = f"/api/v1/map/markers/{marker['id']}"
    response = await api_client.patch(url, headers=headers, json=payload)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["snapshot"]["previous_building"]["id"] == building["id"]
    assert detail["snapshot"]["target_building"]["id"] == second["id"]
    assert (await api_client.get(url, headers=headers)).json()["building_id"] == building["id"]
    confirmed = await api_client.patch(url, headers=headers, json={**payload, "binding_confirmation": detail["confirmation_token"]})
    assert confirmed.status_code == 200 and confirmed.json()["id"] == marker["id"]
    assert confirmed.json()["building_id"] == second["id"]
    assert await db_session.scalar(select(func.count()).select_from(MapMarker)) == 1


@pytest.mark.asyncio
async def test_unlink_primary_does_not_delete_or_rewire_house_cables(db_session, api_client):
    _, _, headers, building, _, line = await route_context(db_session, api_client)
    marker = (await api_client.get(f"/api/v1/map/buildings/{building['id']}/marker", headers=headers)).json()
    response = await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers,
        json={"expected_version": marker["version"], "building_id": None, "building_link_role": "none"})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == marker["id"] and response.json()["latitude"] == marker["latitude"]
    fresh = (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json()
    assert fresh["source"]["kind"] == "building" and fresh["source"]["id"] == building["id"]
    assert fresh["geometry"] == line["geometry"]
    assert (await api_client.delete(f"/api/v1/map/markers/{marker['id']}", headers=headers, params={"expected_version": response.json()["version"]})).status_code == 204
    assert await db_session.get(Building, building["id"]) is not None
    assert await db_session.get(MapConnection, line["id"]) is not None


@pytest.mark.asyncio
async def test_bounded_marker_dependencies_and_delete_versions_do_not_expose_private_lines(db_session, api_client):
    company, _, headers, _ = await marker_building_context(db_session, api_client)
    _, owner = await reader(db_session, api_client, company, "private-route-owner")
    a = await point(api_client, headers, point_type="cabinet", visibility="company")
    b = await point(api_client, headers, point_type="pole", visibility="company", latitude=55.7)
    response = await api_client.post("/api/v1/map/connections", headers=owner, json=cable(
        {"kind": "marker", "id": a["id"]}, {"kind": "marker", "id": b["id"]}, visibility="private", name="НЕ РАСКРЫВАТЬ"))
    assert response.status_code == 201, response.text
    dependencies = await api_client.get(f"/api/v1/map/objects/marker/{a['id']}/dependencies", headers=headers)
    assert dependencies.status_code == 200
    assert dependencies.json()["dependencies"] == [{"type": "restricted", "message": "Есть связанные записи, недоступные в текущем контексте. Обратитесь к ответственному за эти объекты."}]
    blocked = await api_client.delete(f"/api/v1/map/markers/{a['id']}", headers=headers, params={"expected_version": a["version"]})
    assert blocked.status_code == 409 and "НЕ РАСКРЫВАТЬ" not in blocked.text
    assert "dependencies" in blocked.json()["detail"]
    stale = await api_client.delete(f"/api/v1/map/markers/{b['id']}", headers=headers, params={"expected_version": 100})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_version"
    assert await db_session.get(MapMarker, a["id"]) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["split", "route-objects"])
async def test_route_operations_inherit_manual_layers_atomically(db_session, api_client, operation):
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    item = await layer(api_client, headers)
    item = await member(api_client, headers, item, "connection", line["id"])
    payload = split_payload(line)
    if operation == "route-objects": payload["marker"].update(point_type="chamber", icon_name="chamber")
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/{operation}", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    markers = await api_client.get("/api/v1/map/markers", headers=headers, params=selected(item))
    assert [marker["id"] for marker in markers.json()] == [result["marker"]["id"]]
    connections = (await api_client.get("/api/v1/map/connections", headers=headers, params=selected(item))).json()
    assert len(connections) == (2 if operation == "split" else 1)
    assert (await api_client.get(f"/api/v1/map/objects/marker/{result['marker']['id']}/layers", headers=headers)).json()[0]["id"] == item["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["split", "route-objects"])
async def test_layer_inheritance_failure_rolls_back_the_entire_route_operation(db_session, api_client, monkeypatch, operation):
    from services import map_layers
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    item = await layer(api_client, headers)
    item = await member(api_client, headers, item, "connection", line["id"])
    original = map_layers.inherit_route_layers

    async def fail_after_membership_insert(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("injected layer membership failure")

    payload = split_payload(line)
    if operation == "route-objects":
        payload["marker"].update(point_type="chamber", icon_name="chamber")
    with monkeypatch.context() as patch:
        patch.setattr(map_layers, "inherit_route_layers", fail_after_membership_insert)
        with pytest.raises(RuntimeError, match="layer membership failure"):
            await api_client.post(f"/api/v1/map/connections/{line['id']}/{operation}", headers=headers, json=payload)
    assert (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json() == line
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MapLayerMember)) == 1
    assert (await api_client.get("/api/v1/map/layers", headers=headers)).json()[0]["version"] == item["version"]
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.point_type.in_(["splice", "chamber"]))) == 0


@pytest.mark.asyncio
async def test_layer_query_plan_uses_real_postgresql_and_applies_filter_before_limit(db_session, api_client):
    from sqlalchemy.dialects import postgresql
    from services.map_layers import map_predicates
    from core.map_domain import visible_to
    from schemas.map_workspace import MapFilter
    company, _, headers, _ = await marker_building_context(db_session, api_client)
    item = await layer(api_client, headers)
    points = [MapMarker(company_id=company, name=f"Точка {i}", visibility="company", point_type="cabinet", building_link_role="none", latitude=55.5, longitude=38 + i * .00001) for i in range(1000)]
    db_session.add_all(points); await db_session.flush()
    db_session.add_all([MapLayerMember(company_id=company, layer_id=item["id"], marker_id=point.id) for point in points[-20:]])
    await db_session.flush(); await db_session.execute(text("ANALYZE map_markers, map_layer_members, map_layers"))
    query = select(MapMarker.id).where(*visible_to(MapMarker, company, 1),
        *await map_predicates(db_session, company_id=company, kind="marker", filters=MapFilter(layers_active=True, layer_ids=[item["id"]], include_unassigned=False))).order_by(MapMarker.id).limit(10)
    assert list((await db_session.scalars(query)).all()) == [point.id for point in points[-20:-10]]
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    plan = (await db_session.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql))).scalar_one()[0]
    assert plan["Plan"]["Actual Rows"] == 10
    print("layer-plan:", plan)
    baseline = select(MapMarker.id).where(*visible_to(MapMarker, company, 1)).order_by(MapMarker.id).limit(10)
    baseline_sql = str(baseline.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    print("unfiltered-plan:", (await db_session.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + baseline_sql))).scalar_one()[0])
    dynamic = await layer(api_client, headers, mode="dynamic", rules={"point_types": ["cabinet"]})
    dynamic_query = select(MapMarker.id).where(*visible_to(MapMarker, company, 1),
        *await map_predicates(db_session, company_id=company, kind="marker", filters=MapFilter(layers_active=True, layer_ids=[dynamic["id"]], include_unassigned=False))).order_by(MapMarker.id).limit(10)
    dynamic_sql = str(dynamic_query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    print("dynamic-plan:", (await db_session.execute(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + dynamic_sql))).scalar_one()[0])
