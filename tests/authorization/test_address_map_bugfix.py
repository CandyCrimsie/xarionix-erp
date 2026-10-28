import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from core.map_domain import MapOperationError
from models.buildings import Building
from models.company import Company
from models.locations import Location
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from schemas.map_markers import MapMarkerUpdate
from services.map_markers import update_marker
from test_map_api import marker_building_context, primary_marker, represents_payload
from test_map_graph_api import cable, point, reader


@pytest.mark.asyncio
async def test_delete_conflict_lists_real_connections_entrances_locations_without_mutation(db_session, api_client):
    company, _, headers, building = await marker_building_context(db_session, api_client)
    assert (await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": 55.57, "longitude": 38.24})).status_code == 200
    node = await point(api_client, headers, name="Узел A", point_type="network_node", visibility="company")
    for medium in ("fiber", "utp"):
        response = await api_client.post("/api/v1/map/connections", headers=headers, json=cable(
            {"kind": "marker", "id": node["id"]}, {"kind": "building", "id": building["id"]},
            name=f"Кабель {medium}", medium=medium, fiber_count=24 if medium == "fiber" else None))
        assert response.status_code == 201, response.text
    for number in ("1", "2"):
        assert (await api_client.post(f"/api/v1/buildings/{building['id']}/entrances", headers=headers, json={"number": number})).status_code == 201
    for number in range(3):
        assert (await api_client.post("/api/v1/locations", headers=headers, json={"building_id": building["id"], "name": f"Помещение {number}"})).status_code == 201
    response = await api_client.delete(f"/api/v1/buildings/{building['id']}", headers=headers)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "object_has_dependencies" and detail["object"] == {"kind": "building", "id": building["id"]}
    groups = {group["type"]: group for group in detail["dependencies"]}
    assert groups["entrance"]["count"] == 2 and groups["location"]["count"] == 3
    connections = groups["map_connection"]
    assert connections["count"] == 2 and {item["medium"] for item in connections["items"]} == {"fiber", "utp"}
    assert all(item["source_name"] == "Узел A" and "53" in item["target_name"] for item in connections["items"])
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 2
    assert await db_session.get(Building, building["id"]) is not None
    assert await db_session.scalar(select(func.count()).select_from(Location)) == 3


@pytest.mark.asyncio
async def test_delete_conflict_does_not_disclose_private_or_foreign_company_data(db_session, api_client):
    company, _, headers, building = await marker_building_context(db_session, api_client)
    assert (await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": 55.57, "longitude": 38.24})).status_code == 200
    _, private_headers = await reader(db_session, api_client, company, "private-blocker-owner")
    private = await point(api_client, private_headers, name="СЕКРЕТНАЯ ТОЧКА")
    created = await api_client.post("/api/v1/map/connections", headers=private_headers, json=cable(
        {"kind": "marker", "id": private["id"]}, {"kind": "building", "id": building["id"]}, name="СЕКРЕТНЫЙ КАБЕЛЬ", visibility="private"))
    assert created.status_code == 201, created.text
    foreign = Company(name="Другая компания")
    db_session.add(foreign)
    await db_session.flush()
    db_session.add(Location(company_id=foreign.id, building_id=building["id"], name="СЕКРЕТНОЕ ПОМЕЩЕНИЕ"))
    await db_session.commit()
    response = await api_client.delete(f"/api/v1/buildings/{building['id']}", headers=headers)
    assert response.status_code == 409
    assert "СЕКРЕТ" not in response.text
    groups = response.json()["detail"]["dependencies"]
    assert len(groups) == 1 and groups[0]["type"] == "restricted"
    assert set(groups[0]) == {"type", "message"}
    assert (await api_client.get(f"/api/v1/map/markers/{private['id']}", headers=private_headers)).status_code == 200
    assert (await api_client.get(f"/api/v1/map/connections/{created.json()['id']}", headers=private_headers)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["represents", "reference", "located_at"])
async def test_deleting_unoccupied_house_preserves_independent_marker(db_session, api_client, role):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await primary_marker(api_client, headers, building) if role == "represents" else await point(
        api_client, headers, name="Самостоятельный шкаф", point_type="cabinet", visibility="company", building_id=building["id"], building_link_role=role)
    position = (marker["latitude"], marker["longitude"])
    assert (await api_client.delete(f"/api/v1/buildings/{building['id']}", headers=headers)).status_code == 204
    saved = (await api_client.get(f"/api/v1/map/markers/{marker['id']}", headers=headers)).json()
    assert saved["id"] == marker["id"] and saved["building_id"] is None and saved["building_link_role"] == "none"
    assert (saved["latitude"], saved["longitude"]) == position


@pytest.mark.asyncio
async def test_patch_reference_into_primary_preserves_id_and_writes_canonical_position(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await point(api_client, headers, point_type="building", visibility="company")
    payload = {"building_id": building["id"], "building_link_role": "represents", "expected_version": marker["version"],
        "building_position": {"latitude": 55.577276, "longitude": 38.245099}}
    response = await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["id"] == marker["id"] and saved["version"] == marker["version"] + 1
    assert await db_session.scalar(select(func.count()).select_from(MapMarker)) == 1
    canonical = (await api_client.get(f"/api/v1/buildings/{building['id']}", headers=headers)).json()
    assert float(canonical["latitude"]) == saved["latitude"] == 55.577276
    row = await db_session.get(MapMarker, marker["id"])
    assert row.latitude is None and row.longitude is None
    assert (await api_client.get(f"/api/v1/map/buildings/{building['id']}/marker", headers=headers)).json()["id"] == marker["id"]
    repeated = await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers, json=payload)
    assert repeated.status_code == 409


@pytest.mark.asyncio
async def test_replacing_primary_returns_atomic_binding_effects(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    old = await primary_marker(api_client, headers, building)
    extra = await point(api_client, headers, point_type="building", visibility="company")
    payload = {"building_id": building["id"], "building_link_role": "represents", "expected_version": extra["version"]}
    conflict = await api_client.patch(f"/api/v1/map/markers/{extra['id']}", headers=headers, json=payload)
    assert conflict.status_code == 409
    confirmed = await api_client.patch(f"/api/v1/map/markers/{extra['id']}", headers=headers,
        json={**payload, "binding_confirmation": conflict.json()["detail"]["confirmation_token"]})
    assert confirmed.status_code == 200, confirmed.text
    saved = confirmed.json()
    assert saved["id"] == extra["id"]
    assert saved["binding_effects"] == [{"id": old["id"], "building_id": building["id"], "building_link_role": "reference",
        "latitude": old["latitude"], "longitude": old["longitude"], "version": old["version"] + 1}]
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.building_link_role == "represents")) == 1


@pytest.mark.asyncio
async def test_parallel_marker_patch_has_one_winner_without_new_records(db_session, api_client):
    company, _, headers, _ = await marker_building_context(db_session, api_client)
    marker = await point(api_client, headers, point_type="cabinet", visibility="company")
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)

    async def attempt(name):
        async with factory() as session:
            try:
                return await update_marker(session, company_id=company, user_id=1, can_manage=True, marker_id=marker["id"],
                    data=MapMarkerUpdate(name=name, expected_version=marker["version"]))
            except MapOperationError as error:
                return error.detail["code"]

    await db_session.commit()
    results = await asyncio.gather(attempt("Первое изменение"), attempt("Второе изменение"))
    assert results.count("stale_version") == 1
    assert await db_session.scalar(select(func.count()).select_from(MapMarker)) == 1


@pytest.mark.asyncio
async def test_rebinding_patch_rolls_back_marker_and_house_together(db_session, api_client, monkeypatch):
    from services import map_markers
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await point(api_client, headers, point_type="building", visibility="company")

    async def failure(*args, **kwargs):
        raise RuntimeError("injected canonical position failure")

    with monkeypatch.context() as patch:
        patch.setattr(map_markers, "set_building_position", failure)
        with pytest.raises(RuntimeError, match="canonical position"):
            await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers, json={
                "building_id": building["id"], "building_link_role": "represents", "expected_version": marker["version"],
                "building_position": {"latitude": 55.5, "longitude": 38.2}})
    assert (await api_client.get(f"/api/v1/map/markers/{marker['id']}", headers=headers)).json() == marker
    assert (await api_client.get(f"/api/v1/buildings/{building['id']}", headers=headers)).json()["latitude"] is None


@pytest.mark.asyncio
async def test_concurrent_house_delete_and_connection_creation_returns_404_not_500(db_session, api_client, monkeypatch):
    from services import map_connections
    from schemas.map_connections import MapConnectionCreate
    company, _, headers, building = await marker_building_context(db_session, api_client)
    assert (await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": 55.57, "longitude": 38.24})).status_code == 200
    node = await point(api_client, headers, point_type="cabinet", visibility="company")
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)
    entered = asyncio.Event()
    original = map_connections.lock_buildings

    async def notify(session, ids):
        entered.set()
        return await original(session, ids)

    async def create():
        async with factory() as session:
            try:
                return await map_connections.save_connection(session, company_id=company, user_id=1, can_manage=True,
                    data=MapConnectionCreate.model_validate(cable({"kind": "building", "id": building["id"]}, {"kind": "marker", "id": node["id"]})))
            except MapOperationError as error:
                return error

    await db_session.commit()
    async with factory() as deleting:
        locked = await deleting.scalar(select(Building).where(Building.id == building["id"]).with_for_update())
        with monkeypatch.context() as patch:
            patch.setattr(map_connections, "lock_buildings", notify)
            task = asyncio.create_task(create())
            await asyncio.wait_for(entered.wait(), 3)
            await deleting.delete(locked)
            await deleting.commit()
            result = await asyncio.wait_for(task, 3)
    assert isinstance(result, MapOperationError) and result.status == 404
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 0
