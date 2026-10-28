import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.map_domain import MapOperationError
from core.map_geometry import segment_position
from models.map_connections import MapConnection
from models.company_memberships import CompanyMembership
from models.membership_roles import MembershipRole
from models.roles import Role
from models.map_markers import MapMarker
from schemas.map_connections import MapConnectionSplit
from services.map_connections import split_connection
from test_map_api import marker_building_context, primary_marker
from test_map_graph_api import cable, point, reader


async def route_context(session, client, **overrides):
    company, token, headers, building = await marker_building_context(session, client)
    a = await primary_marker(client, headers, building)
    b = await point(client, headers, name="Узел Б", visibility="company", point_type="network_node", latitude=55.59, longitude=38.27)
    response = await client.post("/api/v1/map/connections", headers=headers, json=cable(
        {"kind": "marker", "id": a["id"]}, {"kind": "marker", "id": b["id"]},
        vertices=[[38.25, 55.58], [38.26, 55.585]], description="Сохраняем трассу", **overrides))
    assert response.status_code == 201, response.text
    return company, token, headers, building, b, response.json()


def split_payload(line, index=1, fraction=.37):
    points = line["geometry"]["coordinates"]
    lng, lat = segment_position(points[index], points[index + 1], fraction)
    return {"expected_version": line["version"], "expected_geometry_token": line["geometry_token"],
        "segment_index": index, "fraction": fraction, "position": {"latitude": lat, "longitude": lng},
        "marker": {"name": "Муфта М", "description": "На повороте трассы", "icon_name": "splice", "background_enabled": False}}


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility,medium", [("company", "fiber"), ("private", "utp")])
async def test_split_preserves_topology_geometry_and_cable(db_session, api_client, visibility, medium):
    _, _, headers, _, _, line = await route_context(db_session, api_client, visibility=visibility, medium=medium,
        fiber_count=48 if medium == "fiber" else None, category="Cat 6A" if medium == "utp" else None)
    payload = split_payload(line)
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    marker, (first, second) = result["marker"], result["connections"]
    m = [marker["longitude"], marker["latitude"]]
    assert marker["point_type"] == "splice" and marker["building_id"] is None
    assert marker["background_enabled"] is False
    assert first["id"] == line["id"] and first["version"] == line["version"] + 1
    assert first["target"]["id"] == second["source"]["id"] == marker["id"]
    assert first["target"]["kind"] == second["source"]["kind"] == "marker"
    assert first["geometry"]["coordinates"] == [*line["geometry"]["coordinates"][:2], m]
    assert second["geometry"]["coordinates"] == [m, *line["geometry"]["coordinates"][2:]]
    for item in (marker, first, second):
        assert item["visibility"] == line["visibility"]
        assert item["owner_user_id"] == line["owner_user_id"]
    for key in ("name", "description", "medium", "fiber_count", "category", "status"):
        assert first[key] == second[key] == line[key]
    assert first["length_m"] + second["length_m"] == pytest.approx(line["length_m"], abs=.02)
    # Repeated submit is a conflict, not a second splice.
    repeated = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=payload)
    assert repeated.status_code == 409 and repeated.json()["detail"]["code"] == "stale_version"
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 2


@pytest.mark.asyncio
async def test_split_on_bend_removes_only_duplicate_vertex(db_session, api_client):
    *_, headers, building, node, line = await route_context(db_session, api_client)
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(line, 1, 1))
    assert response.status_code == 201, response.text
    first, second = response.json()["connections"]
    assert first["geometry"]["coordinates"] == line["geometry"]["coordinates"][:3]
    assert second["geometry"]["coordinates"] == line["geometry"]["coordinates"][2:]
    assert len(second["geometry"]["coordinates"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change,code", [
    ({"expected_version": 5}, "stale_version"),
    ({"segment_index": 99}, "invalid_segment"),
    ({"position": {"longitude": 38.1, "latitude": 55.1}}, "off_route"),
])
async def test_split_rejects_stale_and_off_line_points(db_session, api_client, change, code):
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json={**split_payload(line), **change})
    assert response.status_code in (409, 422), response.text
    assert response.json()["detail"]["code"] == code
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.point_type == "splice")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["building", "marker"])
async def test_split_detects_live_endpoint_moves_without_connection_version_change(db_session, api_client, which):
    _, _, headers, building, node, line = await route_context(db_session, api_client)
    path = f"/api/v1/buildings/{building['id']}" if which == "building" else f"/api/v1/map/markers/{node['id']}"
    moved = await api_client.patch(path, headers=headers, json={"latitude": 55.6, "longitude": 38.3})
    assert moved.status_code == 200, moved.text
    fresh = (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json()
    assert fresh["version"] == line["version"] and fresh["geometry_token"] != line["geometry_token"]
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(line))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "stale_geometry"


@pytest.mark.asyncio
async def test_split_rejects_endpoints_and_degenerate_segments(db_session, api_client):
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    for fraction in (0, .00001):
        response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(line, 0, fraction))
        assert response.status_code == 422 and response.json()["detail"]["code"] == "near_endpoint"
    # A repeated internal vertex is legal existing data; it must not crash snapping/splitting.
    payload = {key: line[key] for key in ("source", "target", "visibility", "name", "medium", "status", "fiber_count", "category")}
    payload["source"] = {key: line["source"][key] for key in ("kind", "id")}
    payload["target"] = {key: line["target"][key] for key in ("kind", "id")}
    changed = await api_client.patch(f"/api/v1/map/connections/{line['id']}", headers=headers,
        json={**payload, "expected_version": 1, "vertices": [[38.25, 55.58], [38.25, 55.58]]})
    assert changed.status_code == 200, changed.text
    line = changed.json()
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(line))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "degenerate_segment"


@pytest.mark.asyncio
async def test_split_auth_permissions_private_ownership_and_company_isolation(db_session, api_client):
    company, _, headers, building, node, line = await route_context(db_session, api_client)
    _, read_headers = await reader(db_session, api_client, company, "split-reader")
    url = f"/api/v1/map/connections/{line['id']}/split"
    assert (await api_client.post(url, json=split_payload(line))).status_code == 401
    assert (await api_client.post(url, headers=read_headers, json=split_payload(line))).status_code == 403
    private = await api_client.post("/api/v1/map/connections", headers=headers, json=cable(
        {"kind": "building", "id": building["id"]}, {"kind": "marker", "id": node["id"]}, visibility="private"))
    private = private.json()
    assert (await api_client.post(f"/api/v1/map/connections/{private['id']}/split", headers=read_headers, json=split_payload(private, 0))).status_code == 404
    # Even a reader who owns a personal route cannot create a technical object.
    own = await api_client.post("/api/v1/map/connections", headers=read_headers, json=cable(
        {"kind": "building", "id": building["id"]}, {"kind": "marker", "id": node["id"]}, visibility="private"))
    assert own.status_code == 201, own.text
    own = own.json()
    assert (await api_client.post(f"/api/v1/map/connections/{own['id']}/split", headers=read_headers, json=split_payload(own, 0))).status_code == 403
    # A valid administrator of another company cannot learn whether it exists.
    from models.company import Company
    from test_map_api import company_headers
    other = Company(name="Другая компания", short_name="Б")
    db_session.add(other)
    await db_session.flush()
    admin = (await api_client.get("/api/v1/auth/me", headers=headers)).json()["id"]
    membership = CompanyMembership(company_id=other.id, user_id=admin)
    db_session.add(membership)
    await db_session.flush()
    from services.system_roles import sync_system_roles_for_company_in_transaction
    await sync_system_roles_for_company_in_transaction(db_session, company_id=other.id)
    role = await db_session.scalar(select(Role.id).where(Role.company_id == other.id, Role.system_key == "administrator"))
    db_session.add(MembershipRole(company_membership_id=membership.id, role_id=role))
    other_id = other.id
    await db_session.commit()
    foreign = {**headers, "X-Company-Id": str(other_id)}
    assert (await api_client.get("/api/v1/map/connections", headers=foreign)).status_code == 200
    assert (await api_client.post(url, headers=foreign, json=split_payload(line))).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"fraction": -1}, {"fraction": 1.01}, {"segment_index": True}, {"expected_version": None},
    {"marker": {"name": "М", "owner_user_id": 1}}, {"company_id": 1},
    {"marker": {"name": "М", "point_type": "note"}}, {"marker": {"name": "<svg/>"}},
])
async def test_split_contract_validation(db_session, api_client, override):
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json={**split_payload(line), **override})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_split_rolls_back_if_tail_insert_fails(db_session, api_client, monkeypatch):
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    original_flush = AsyncSession.flush

    async def fail_tail(session, *args, **kwargs):
        if any(isinstance(entity, MapConnection) for entity in session.new):
            raise RuntimeError("injected tail insert failure")
        return await original_flush(session, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "flush", fail_tail)
        with pytest.raises(RuntimeError, match="tail insert"):
            await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(line))
    fresh = (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json()
    assert fresh == line
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.point_type == "splice")) == 0


@pytest.mark.asyncio
async def test_parallel_split_has_exactly_one_winner(db_session, api_client):
    company, _, headers, _, _, line = await route_context(db_session, api_client, visibility="private")
    owner = line["owner_user_id"]
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)
    data = MapConnectionSplit.model_validate(split_payload(line))

    async def attempt():
        async with factory() as session:
            try:
                return await split_connection(session, company_id=company, user_id=owner, can_manage=True, connection_id=line["id"], data=data)
            except MapOperationError as exc:
                return exc

    # Release the read transaction before independent real PostgreSQL sessions.
    await db_session.commit()
    results = await asyncio.gather(attempt(), attempt())
    assert sum(isinstance(item, MapOperationError) for item in results) == 1
    failure = next(item for item in results if isinstance(item, MapOperationError))
    assert failure.detail["code"] == "stale_version"
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 2
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.point_type == "splice")) == 1


@pytest.mark.asyncio
async def test_split_changes_only_explicit_route_not_an_overlapping_cable(db_session, api_client):
    _, _, headers, building, node, line = await route_context(db_session, api_client)
    created = await api_client.post("/api/v1/map/connections", headers=headers, json=cable(
        {"kind": "building", "id": building["id"]}, {"kind": "marker", "id": node["id"]},
        name="Другой кабель в той же трассе", vertices=line["vertices"]))
    assert created.status_code == 201
    other = created.json()
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(line))
    assert response.status_code == 201
    assert (await api_client.get(f"/api/v1/map/connections/{other['id']}", headers=headers)).json() == other
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 3


@pytest.mark.asyncio
async def test_split_deleted_route_and_user_without_read(db_session, api_client):
    company, _, headers, _, _, line = await route_context(db_session, api_client)
    from services.auth import register_user
    from test_map_api import company_headers
    user = await register_user(db_session, username="no-map-read", password="password123")
    db_session.add(CompanyMembership(company_id=company, user_id=user.id))
    await db_session.commit()
    login = await api_client.post("/api/v1/auth/login", json={"username": "no-map-read", "password": "password123"})
    restricted = company_headers(login.json()["access_token"], company)
    url = f"/api/v1/map/connections/{line['id']}/split"
    assert (await api_client.post(url, headers=restricted, json=split_payload(line))).status_code == 403
    assert (await api_client.delete(f"/api/v1/map/connections/{line['id']}", headers=headers)).status_code == 204
    assert (await api_client.post(url, headers=headers, json=split_payload(line))).status_code == 404
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.point_type == "splice")) == 0
