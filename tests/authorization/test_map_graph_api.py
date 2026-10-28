import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from models.company_memberships import CompanyMembership
from models.membership_roles import MembershipRole
from models.roles import Role
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from models.company import Company
from services.auth import register_user
from test_map_api import (company_headers, create_building, marker_building_context, marker_payload, primary_marker)


async def reader(session, client, company_id, username):
    user = await register_user(session, username=username, password="password123")
    membership = CompanyMembership(company_id=company_id, user_id=user.id)
    session.add(membership)
    await session.flush()
    role_id = await session.scalar(select(Role.id).where(Role.company_id == company_id, Role.system_key == "employee"))
    session.add(MembershipRole(company_membership_id=membership.id, role_id=role_id))
    await session.commit()
    response = await client.post("/api/v1/auth/login", json={"username": username, "password": "password123"})
    assert response.status_code == 200
    return user.id, company_headers(response.json()["access_token"], company_id)


async def point(client, headers, **kwargs):
    response = await client.post("/api/v1/map/markers", headers=headers, json=marker_payload(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def cable(source, target, **kwargs):
    return {"source": source, "target": target, "name": "Магистраль", "medium": "fiber", "fiber_count": 24, "status": "active", "vertices": [], **kwargs}


@pytest.mark.asyncio
async def test_private_points_styles_and_connections_are_owner_scoped(db_session, api_client, clean_test_redis):
    company, _, admin_headers, building = await marker_building_context(db_session, api_client)
    user_a, headers_a = await reader(db_session, api_client, company, "reader-a")
    _, headers_b = await reader(db_session, api_client, company, "reader-b")
    a = await point(api_client, headers_a, name="Личная заметка", visibility="private", point_type="note")
    assert a["owner_user_id"] == user_a
    assert a["can_manage"] is True
    for headers in (headers_b, admin_headers):
        assert (await api_client.get(f"/api/v1/map/markers/{a['id']}", headers=headers)).status_code == 404
        assert (await api_client.patch(f"/api/v1/map/markers/{a['id']}", headers=headers, json={"name": "Чужое"})).status_code == 404
        assert (await api_client.delete(f"/api/v1/map/markers/{a['id']}", headers=headers)).status_code == 404
        assert (await api_client.get("/api/v1/map/markers", headers=headers)).json() == []
        assert (await api_client.get("/api/v1/map/endpoints", headers=headers, params={"q": "Личная"})).json()["items"] == []
    denied = await api_client.post("/api/v1/map/markers", headers=headers_a, json=marker_payload(visibility="company"))
    assert denied.status_code == 403
    b = await point(api_client, headers_a, name="Вторая заметка", latitude=55.6)
    payload = cable({"kind": "marker", "id": a["id"]}, {"kind": "marker", "id": b["id"]}, visibility="private")
    response = await api_client.post("/api/v1/map/connections", headers=headers_a, json=payload)
    assert response.status_code == 201, response.text
    connection = response.json()
    assert connection["owner_user_id"] == user_a
    assert (await api_client.get("/api/v1/map/connections", headers=headers_b)).json() == []
    assert (await api_client.get(f"/api/v1/map/connections/{connection['id']}", headers=headers_b)).status_code == 404
    assert (await api_client.patch(f"/api/v1/map/connections/{connection['id']}", headers=headers_b, json={**payload, "expected_version": 1})).status_code == 404
    assert (await api_client.delete(f"/api/v1/map/connections/{connection['id']}", headers=headers_b)).status_code == 404
    # Public endpoints cannot reveal another owner's private object by ID.
    public = await api_client.post("/api/v1/map/connections", headers=admin_headers, json={**payload, "visibility": "company"})
    assert public.status_code == 404
    own_public = await api_client.post("/api/v1/map/connections", headers=headers_a, json={**payload, "visibility": "company"})
    assert own_public.status_code == 403
    style = {"name": "Мой стиль", "appearance": {"icon_name": "network-node", "icon_color": "#465366"}}
    preset = await api_client.post("/api/v1/map/marker-styles", headers=headers_a, json=style)
    assert preset.status_code == 201, preset.text
    preset = preset.json()
    for headers in (headers_b, admin_headers):
        assert (await api_client.get("/api/v1/map/marker-styles", headers=headers)).json() == []
        assert (await api_client.get(f"/api/v1/map/marker-styles/{preset['id']}", headers=headers)).status_code == 404
        assert (await api_client.delete(f"/api/v1/map/marker-styles/{preset['id']}", headers=headers)).status_code == 404
    changed = await api_client.patch(f"/api/v1/map/marker-styles/{preset['id']}", headers=headers_a, json={**style, "name": "Новый стиль", "expected_version": 1})
    assert changed.status_code == 200, changed.text
    stale = await api_client.patch(f"/api/v1/map/marker-styles/{preset['id']}", headers=headers_a, json={**style, "expected_version": 1})
    assert stale.status_code == 409
    assert (await api_client.delete(f"/api/v1/map/marker-styles/{preset['id']}", headers=headers_a)).status_code == 204


@pytest.mark.asyncio
async def test_route_endpoints_are_live_and_building_representation_is_not_an_endpoint(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    primary = await primary_marker(api_client, headers, building)
    node = await point(api_client, headers, point_type="cabinet", visibility="company", icon_name="cabinet", name="Шкаф", latitude=56, longitude=40)
    # Numeric IDs may coincide; discriminators keep the endpoint identities.
    payload = cable({"kind": "marker", "id": primary["id"]}, {"kind": "marker", "id": node["id"]}, vertices=[[39, 55.7]])
    created = await api_client.post("/api/v1/map/connections", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    connection = created.json()
    assert connection["source"]["kind"] == "building"
    assert connection["source"]["id"] == building["id"]
    assert "Гагарина" in connection["source"]["name"]
    assert connection["geometry"]["coordinates"][1] == [39, 55.7]
    assert connection["length_m"] > 1000
    moved = await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": 55.9, "longitude": 38.8})
    assert moved.status_code == 200
    refreshed = (await api_client.get(f"/api/v1/map/connections/{connection['id']}", headers=headers)).json()
    assert refreshed["geometry"]["coordinates"] == [[38.8, 55.9], [39, 55.7], [40, 56]]
    replacement = await api_client.post("/api/v1/map/markers", headers=headers, json={**marker_payload(), "point_type": "building", "visibility": "company", "building_id": building["id"], "building_link_role": "represents"})
    assert replacement.status_code == 409
    token = replacement.json()["detail"]["confirmation_token"]
    replaced = await api_client.post("/api/v1/map/markers", headers=headers, json={**marker_payload(), "point_type": "building", "visibility": "company", "building_id": building["id"], "building_link_role": "represents", "binding_confirmation": token})
    assert replaced.status_code == 201, replaced.text
    assert (await api_client.get(f"/api/v1/map/connections/{connection['id']}", headers=headers)).json()["source"]["id"] == building["id"]
    assert (await api_client.delete(f"/api/v1/map/markers/{node['id']}", headers=headers)).status_code == 409
    assert (await api_client.delete(f"/api/v1/buildings/{building['id']}", headers=headers)).status_code == 409
    assert (await api_client.patch(f"/api/v1/map/markers/{node['id']}", headers=headers, json={"visibility": "private"})).status_code == 409
    cleared = await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": None, "longitude": None})
    assert cleared.status_code == 200
    missing = (await api_client.get(f"/api/v1/map/connections/{connection['id']}", headers=headers)).json()
    assert missing["geometry"] is None and missing["position_missing"] is True
    assert (await api_client.delete(f"/api/v1/map/connections/{connection['id']}", headers=headers)).status_code == 204
    assert (await api_client.get(f"/api/v1/map/markers/{node['id']}", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_viewport_uses_actual_segments_including_external_endpoints(db_session, api_client):
    _, _, headers, _ = await marker_building_context(db_session, api_client)
    a = await point(api_client, headers, visibility="company", point_type="network_node", latitude=55, longitude=35)
    b = await point(api_client, headers, visibility="company", point_type="network_node", latitude=55, longitude=45)
    payload = cable({"kind": "marker", "id": a["id"]}, {"kind": "marker", "id": b["id"]})
    created = await api_client.post("/api/v1/map/connections", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    crossing = await api_client.get("/api/v1/map/connections", headers=headers, params={"west": 38, "east": 39, "south": 54, "north": 56})
    assert crossing.status_code == 200, crossing.text
    assert [line["id"] for line in crossing.json()] == [created.json()["id"]]
    outside = await api_client.get("/api/v1/map/connections", headers=headers, params={"west": 38, "east": 39, "south": 57, "north": 58})
    assert outside.status_code == 200 and outside.json() == []
    changed = await api_client.patch(f"/api/v1/map/connections/{created.json()['id']}", headers=headers,
        json={**payload, "medium": "utp", "fiber_count": None, "category": "Cat 6", "vertices": [[38, 55.3]], "expected_version": 1})
    assert changed.status_code == 200, changed.text
    assert changed.json()["fiber_count"] is None
    stale = await api_client.patch(f"/api/v1/map/connections/{created.json()['id']}", headers=headers, json={**payload, "expected_version": 1})
    assert stale.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [
    {"vertices": [[float("inf"), 55]]}, {"vertices": [[1, 91]]}, {"vertices": [[1, 2, 3]]},
    {"vertices": [[1, 2]] * 499}, {"fiber_count": 0}, {"fiber_count": True},
    {"category": "Cat 6"}, {"medium": "utp", "fiber_count": 24},
    {"owner_user_id": 5}, {"name": "<script>alert(1)</script>"},
])
async def test_connection_validation(db_session, api_client, override):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    # Infinity is sent as a string to exercise API validation, not httpx JSON encoding.
    if override.get("vertices") == [[float("inf"), 55]]:
        override = {"vertices": [["Infinity", 55]]}
    response = await api_client.post("/api/v1/map/connections", headers=headers,
        json=cable({"kind": "building", "id": building["id"]}, {"kind": "marker", "id": 1}, **override))
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_upgrade_preserves_ambiguous_legacy_markers_without_arbitrary_primary(db_session, api_client):
    from database.map_upgrade import inspect_legacy_markers, upgrade_map_schema
    _, _, headers, building = await marker_building_context(db_session, api_client)
    await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude":55,"longitude":38})
    # The isolated test schema lives only in this rolled-back transaction.
    async with db_session.bind.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text("CREATE SCHEMA map_upgrade_fixture"))
            await connection.execute(text("SET LOCAL search_path TO map_upgrade_fixture, public"))
            await connection.execute(text("CREATE TABLE map_markers (id bigint PRIMARY KEY, company_id bigint, building_id bigint, sync_building_coordinates boolean, latitude numeric, longitude numeric, name text)"))
            await connection.execute(text("INSERT INTO map_markers VALUES (1, 1, 1, true, 55, 38, 'Первый'), (2, 1, 1, true, 56, 39, 'Второй'), (3, 1, 2, false, 57, 40, 'Ссылка'), (4, 2, 1, true, 55, 38, 'Другой компании'), (5, 2, 999999, true, 58, 41, 'Дом без расположения')"))
            dry = await inspect_legacy_markers(connection)
            assert dry["conflicts"][0]["marker_ids"] == [1, 2]
            assert dry["unpositioned_buildings"][0]["marker_id"] == 5
            await upgrade_map_schema(connection)
            records = (await connection.execute(text("SELECT id, latitude, longitude, building_link_role FROM map_markers ORDER BY id"))).all()
            assert records[:3] == [(1, 55, 38, "reference"), (2, 56, 39, "reference"), (3, 57, 40, "reference")]
            assert records[3] == (4, None, None, "represents")
            assert records[4] == (5, 58, 41, "reference")
            assert await connection.scalar(text("SELECT count(*) FROM map_marker_legacy_backup")) == 5
            assert (await upgrade_map_schema(connection))["upgrade_required"] is False
        finally:
            await transaction.rollback()


@pytest.mark.asyncio
async def test_graph_enforces_jwt_company_and_real_foreign_keys(db_session, api_client):
    company, token, headers, building = await marker_building_context(db_session, api_client)
    for path in ("/map/markers", "/map/connections", "/map/marker-styles", "/map/endpoints?q=Дом"):
        assert (await api_client.get("/api/v1" + path)).status_code == 401
    a = await point(api_client, headers, visibility="company", point_type="cabinet", name="Общий шкаф")
    b = await point(api_client, headers, visibility="company", point_type="cabinet", latitude=56)
    payload = cable({"kind":"marker", "id":a["id"]}, {"kind":"marker", "id":b["id"]})
    line = (await api_client.post("/api/v1/map/connections", headers=headers, json=payload)).json()
    # Give the same administrator valid access to a second company. Access to
    # company B must still not expose records or endpoints of company A.
    other = Company(name="Другая компания")
    db_session.add(other); await db_session.flush()
    admin = (await api_client.get("/api/v1/auth/me", headers=headers)).json()["id"]
    membership = CompanyMembership(company_id=other.id, user_id=admin)
    db_session.add(membership); await db_session.flush()
    from services.system_roles import sync_system_roles_for_company_in_transaction
    await sync_system_roles_for_company_in_transaction(db_session, company_id=other.id)
    role = await db_session.scalar(select(Role.id).where(Role.company_id==other.id, Role.system_key=="administrator"))
    db_session.add(MembershipRole(company_membership_id=membership.id, role_id=role))
    other_id = other.id
    await db_session.commit()
    second = company_headers(token, other_id)
    assert (await api_client.get("/api/v1/map/markers", headers=second)).json() == []
    assert (await api_client.get("/api/v1/map/connections", headers=second)).json() == []
    assert (await api_client.get(f"/api/v1/map/markers/{a['id']}", headers=second)).status_code == 404
    assert (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=second)).status_code == 404
    assert (await api_client.post("/api/v1/map/connections", headers=second, json=payload)).status_code == 404
    # Not just an API convention: composite FKs reject cross-company ends.
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(MapConnection(company_id=other_id, visibility="company", name="Неверная компания",
                source_marker_id=a["id"], target_marker_id=b["id"], medium="fiber", vertices=[]))
            await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(text("DELETE FROM map_markers WHERE id=:id"), {"id": a["id"]})


@pytest.mark.asyncio
async def test_primary_constraint_is_database_enforced_and_zero_length_is_rejected(db_session, api_client):
    company, _, headers, building = await marker_building_context(db_session, api_client)
    await primary_marker(api_client, headers, building)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(MapMarker(company_id=company, building_id=building["id"], point_type="building",
                building_link_role="represents", visibility="company", name="Дублирующая основная метка", latitude=None, longitude=None))
            await db_session.flush()
    a = await point(api_client, headers, name="Первый")
    b = await point(api_client, headers, name="Второй")
    response = await api_client.post("/api/v1/map/connections", headers=headers,
            json=cable({"kind":"marker", "id":a["id"]}, {"kind":"marker", "id":b["id"]}, visibility="private"))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "zero_length"
