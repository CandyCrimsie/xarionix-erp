import asyncio
import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.config import config
from core.permissions.scopes import PermissionScope
from models.company_memberships import CompanyMembership
from models.membership_roles import MembershipRole
from models.permissions import Permission
from models.role_permissions import RolePermission
from models.roles import Role
from models.buildings import Building
from models.map_markers import MapMarker
from schemas.map_markers import MapMarkerCreate
from services import map_markers as marker_service
from services import addresses as address_service
from services.address_types import sync_system_address_types
from services.auth import register_user

# The DB fixture recreates numeric IDs; cached permissions/sessions must not
# survive between otherwise independent map API regression scenarios.
pytestmark = pytest.mark.usefixtures("clean_test_redis")


def company_headers(token: str, company_id: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": str(company_id),
    }


async def initialize_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> tuple[int, str, dict[str, int]]:
    await sync_system_address_types(db_session)
    setup = await api_client.post(
        "/api/v1/setup/initialize",
        json={"company": {"name": "Map Company", "short_name": "MAP"}},
    )
    assert setup.status_code == 201
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "password123"},
    )
    assert login.status_code == 200
    company_id = setup.json()["company_id"]
    token = login.json()["access_token"]
    headers = company_headers(token, company_id)
    types_response = await api_client.get("/api/v1/address-types", headers=headers)
    assert types_response.status_code == 200
    type_ids = {item["code"]: item["id"] for item in types_response.json()}
    return company_id, token, type_ids


async def create_address_object(
    api_client: AsyncClient,
    headers: dict[str, str],
    *,
    type_id: int,
    name: str,
    parent_id: int | None = None,
) -> dict:
    response = await api_client.post(
        "/api/v1/address-objects",
        headers=headers,
        json={"parent_id": parent_id, "type_id": type_id, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_building(
    api_client: AsyncClient,
    headers: dict[str, str],
    *,
    parent_id: int,
    number: str,
    latitude: float | None,
    longitude: float | None,
) -> dict:
    response = await api_client.post(
        f"/api/v1/address-objects/{parent_id}/buildings",
        headers=headers,
        json={
            "address_object_id": parent_id,
            "number": number,
            "corpus": None,
            "structure": None,
            "latitude": latitude,
            "longitude": longitude,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_map_session_is_short_lived_and_matches_nginx_secure_link(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    company_id, token, _ = await initialize_context(db_session, api_client)
    response = await api_client.get(
        "/api/v1/map/session",
        headers=company_headers(token, company_id),
    )
    assert response.status_code == 200
    body = response.json()
    parsed = urlparse(body["tile_url_template"])
    query = parse_qs(parsed.query)
    expires = int(query["expires"][0])
    signature = query["signature"][0]
    expected = base64.urlsafe_b64encode(
        hashlib.md5(
            f"{expires} map-tiles {config.MAP_TILES_SIGNING_SECRET}".encode()
        ).digest()
    ).decode().rstrip("=")

    assert parsed.path == "/map/tiles/{z}/{x}/{y}.png"
    assert signature == expected
    assert expires == body["expires_at"]
    assert body["min_zoom"] == 0
    assert body["max_zoom"] == 20
    assert body["default_latitude"] == config.MAP_DEFAULT_LATITUDE
    assert body["default_longitude"] == config.MAP_DEFAULT_LONGITUDE
    assert body["default_zoom"] == config.MAP_DEFAULT_ZOOM


@pytest.mark.asyncio
async def test_map_session_reports_missing_configuration(
    db_session: AsyncSession,
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    company_id, token, _ = await initialize_context(db_session, api_client)
    monkeypatch.setattr(config, "MAP_TILES_ENABLED", False)
    response = await api_client.get(
        "/api/v1/map/session",
        headers=company_headers(token, company_id),
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Map tiles are not configured"


@pytest.mark.asyncio
async def test_map_buildings_are_filtered_in_postgresql_and_bounds_include_descendants(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    company_id, token, types = await initialize_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city = await create_address_object(
        api_client,
        headers,
        type_id=types["city"],
        name="Раменское",
    )
    street = await create_address_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Гагарина",
        parent_id=city["id"],
    )
    inside = await create_building(
        api_client,
        headers,
        parent_id=street["id"],
        number="53",
        latitude=55.566,
        longitude=38.230,
    )
    await create_building(
        api_client,
        headers,
        parent_id=street["id"],
        number="55",
        latitude=56.500,
        longitude=39.500,
    )
    await create_building(
        api_client,
        headers,
        parent_id=street["id"],
        number="57",
        latitude=None,
        longitude=None,
    )

    response = await api_client.get(
        "/api/v1/map/buildings",
        headers=headers,
        params={"west": 38, "south": 55, "east": 39, "north": 56},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert [feature["id"] for feature in body["features"]] == [inside["id"]]
    assert len({feature["id"] for feature in body["features"]}) == len(
        body["features"]
    )
    feature = body["features"][0]
    assert feature["geometry"] == {
        "type": "Point",
        "coordinates": [38.23, 55.566],
    }
    assert feature["properties"]["full_address"].endswith(
        "Раменское, ул. Гагарина, д. 53"
    )
    assert set(feature["properties"]) == {
        "id",
        "address_object_id",
        "number",
        "corpus",
        "structure",
        "full_address",
    }

    bounds = await api_client.get(
        f"/api/v1/map/address-objects/{city['id']}/bounds",
        headers=headers,
    )
    assert bounds.status_code == 200
    assert bounds.json() == {
        "bounds": {
            "west": 38.23,
            "south": 55.566,
            "east": 39.5,
            "north": 56.5,
        },
        "building_count": 2,
    }


@pytest.mark.asyncio
async def test_map_rejects_invalid_and_overfull_viewports(
    db_session: AsyncSession,
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    company_id, token, types = await initialize_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city = await create_address_object(
        api_client,
        headers,
        type_id=types["city"],
        name="Москва",
    )
    street = await create_address_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Ленина",
        parent_id=city["id"],
    )
    for number, longitude in (("1", 37.61), ("2", 37.62)):
        await create_building(
            api_client,
            headers,
            parent_id=street["id"],
            number=number,
            latitude=55.75,
            longitude=longitude,
        )

    invalid = await api_client.get(
        "/api/v1/map/buildings",
        headers=headers,
        params={"west": 40, "south": 55, "east": 39, "north": 56},
    )
    assert invalid.status_code == 422

    monkeypatch.setattr(config, "MAP_MAX_BUILDINGS_PER_VIEWPORT", 1)
    overfull = await api_client.get(
        "/api/v1/map/buildings",
        headers=headers,
        params={"west": 37, "south": 55, "east": 38, "north": 56},
    )
    assert overfull.status_code == 422
    assert "zoom in" in overfull.json()["detail"]


@pytest.mark.asyncio
async def test_map_endpoints_require_company_and_addresses_read_permission(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    company_id, admin_token, _ = await initialize_context(db_session, api_client)
    assert (await api_client.get("/api/v1/map/session")).status_code == 401
    assert (
        await api_client.get(
            "/api/v1/map/buildings",
            params={"west": 37, "south": 55, "east": 38, "north": 56},
        )
    ).status_code == 401
    user = await register_user(
        db_session,
        username="map-no-access",
        password="password123",
    )
    db_session.add(CompanyMembership(user_id=user.id, company_id=company_id))
    await db_session.commit()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "map-no-access", "password": "password123"},
    )
    headers = company_headers(login.json()["access_token"], company_id)

    assert (await api_client.get("/api/v1/map/session", headers=headers)).status_code == 403
    assert (
        await api_client.get(
            "/api/v1/map/buildings",
            headers=headers,
            params={"west": 37, "south": 55, "east": 38, "north": 56},
        )
    ).status_code == 403
    assert (
        await api_client.get(
            "/api/v1/map/session",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    ).status_code == 400


def marker_payload(**overrides) -> dict:
    payload = {
        "name": "Узел связи №1",
        "description": "Магистральный узел",
        "latitude": 55.577276,
        "longitude": 38.245099,
        "icon_name": "network",
        "label_text": "Узел №1",
        "icon_color": "#FFFFFF",
        "icon_opacity": 0.95,
        "text_color": "#F8FAFC",
        "text_opacity": 0.9,
        "background_enabled": True,
        "background_color": "#2563EB",
        "background_opacity": 0.85,
        "border_enabled": True,
        "border_color": "#FFFFFF",
        "border_width": 2,
        "border_opacity": 0.8,
        "marker_opacity": 1,
        "marker_size": "normal",
        "marker_shape": "rounded",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_map_marker_crud_persists_and_is_company_scoped(
    db_session: AsyncSession,
    api_client: AsyncClient,
):
    company_id, token, _ = await initialize_context(db_session, api_client)
    headers = company_headers(token, company_id)

    created = await api_client.post(
        "/api/v1/map/markers",
        headers=headers,
        json=marker_payload(),
    )
    assert created.status_code == 201, created.text
    marker = created.json()
    assert marker["name"] == "Узел связи №1"
    assert marker["company_id"] == company_id
    assert marker["latitude"] == pytest.approx(55.577276)

    listed = await api_client.get(
        "/api/v1/map/markers",
        headers=headers,
        params={"west": 38, "south": 55, "east": 39, "north": 56},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [marker["id"]]

    updated = await api_client.patch(
        f"/api/v1/map/markers/{marker['id']}",
        headers=headers,
        json={
            "name": "Узел связи №2",
            "longitude": 38.250001,
            "background_enabled": False,
            "border_enabled": False,
            "icon_name": None,
            "marker_shape": "icon",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Узел связи №2"
    assert updated.json()["background_enabled"] is False
    assert updated.json()["icon_name"] is None

    company_b_response = await api_client.post(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Other Map Company", "short_name": "OMAP"},
    )
    assert company_b_response.status_code == 201, company_b_response.text
    headers_b = company_headers(token, company_b_response.json()["id"])
    assert (await api_client.get("/api/v1/map/markers", headers=headers_b)).json() == []
    assert (
        await api_client.get(
            f"/api/v1/map/markers/{marker['id']}", headers=headers_b
        )
    ).status_code == 404
    assert (
        await api_client.patch(
            f"/api/v1/map/markers/{marker['id']}",
            headers=headers_b,
            json={"name": "Чужой маркер"},
        )
    ).status_code == 404
    assert (
        await api_client.delete(
            f"/api/v1/map/markers/{marker['id']}", headers=headers_b
        )
    ).status_code == 404

    deleted = await api_client.delete(
        f"/api/v1/map/markers/{marker['id']}", headers=headers
    )
    assert deleted.status_code == 204
    assert (
        await api_client.get(
            f"/api/v1/map/markers/{marker['id']}", headers=headers
        )
    ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": 91},
        {"longitude": -181},
        {"icon_color": "red"},
        {"icon_opacity": 1.1},
        {"background_opacity": -0.1},
        {"border_width": 9},
        {"icon_name": "not-an-allowed-icon"},
        {"name": "   "},
        {"name": "<svg onload=alert(1)>"},
        {"description": "<script>alert(1)</script>"},
        {"label_text": "x" * 81},
        {"sync_building_coordinates": True},
    ],
)
async def test_map_marker_validation_rejects_unsafe_or_out_of_range_values(
    db_session: AsyncSession,
    api_client: AsyncClient,
    overrides: dict,
):
    company_id, token, _ = await initialize_context(db_session, api_client)
    response = await api_client.post(
        "/api/v1/map/markers",
        headers=company_headers(token, company_id),
        json=marker_payload(**overrides),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_map_marker_permissions_allow_readers_but_deny_management(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, admin_token, _ = await initialize_context(db_session, api_client)
    user = await register_user(
        db_session,
        username="map-marker-reader",
        password="password123",
    )
    membership = CompanyMembership(user_id=user.id, company_id=company_id)
    db_session.add(membership)
    await db_session.flush()
    read_permission = (
        await db_session.execute(
            select(Permission).where(Permission.code == "addresses.read")
        )
    ).scalar_one()
    role = Role(company_id=company_id, name="Map Marker Reader")
    db_session.add(role)
    await db_session.flush()
    db_session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=read_permission.id,
                scope=PermissionScope.COMPANY,
            ),
            MembershipRole(company_membership_id=membership.id, role_id=role.id),
        ]
    )
    await db_session.commit()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "map-marker-reader", "password": "password123"},
    )
    reader_headers = company_headers(login.json()["access_token"], company_id)

    assert (await api_client.get("/api/v1/map/markers", headers=reader_headers)).status_code == 200
    denied = await api_client.post(
        "/api/v1/map/markers",
        headers=reader_headers,
        json=marker_payload(visibility="company"),
    )
    assert denied.status_code == 403
    assert (
        await api_client.post(
            "/api/v1/map/markers",
            headers=company_headers(admin_token, company_id),
            json=marker_payload(),
        )
    ).status_code == 201


async def marker_building_context(db_session, api_client):
    company_id, token, types = await initialize_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city = await create_address_object(
        api_client, headers, type_id=types["city"], name="Раменское"
    )
    street = await create_address_object(
        api_client, headers, type_id=types["street"], name="Гагарина", parent_id=city["id"]
    )
    building = await create_building(
        api_client, headers, parent_id=street["id"], number="53",
        latitude=None, longitude=None,
    )
    return company_id, token, headers, building


def represents_payload(building, **overrides):
    return marker_payload(
        building_id=building["id"], point_type="building", visibility="company",
        building_link_role="represents", **overrides,
    )


async def primary_marker(client, headers, building, **overrides):
    payload = represents_payload(building, **overrides)
    if building["latitude"] is None and "building_position" not in payload:
        payload["building_position"] = {"latitude": 55.577276, "longitude": 38.245099}
    response = await client.post("/api/v1/map/markers", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_primary_marker_uses_canonical_building_position_and_follows_edits(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await primary_marker(api_client, headers, building)
    marker_id = marker["id"]
    stored = await db_session.get(MapMarker, marker_id)
    assert stored.latitude is None and stored.longitude is None
    assert marker["building_link_role"] == "represents"
    assert marker["latitude"] == pytest.approx(55.577276)
    changed = await api_client.patch(
        f"/api/v1/buildings/{building['id']}", headers=headers,
        json={"latitude": 56.1, "longitude": 40.2},
    )
    assert changed.status_code == 200, changed.text
    fetched = (await api_client.get(f"/api/v1/map/markers/{marker_id}", headers=headers)).json()
    assert (fetched["latitude"], fetched["longitude"]) == (56.1, 40.2)
    # Old independent draft fields cannot silently move a positioned house.
    moved = await api_client.patch(
        f"/api/v1/map/markers/{marker_id}", headers=headers,
        json={"latitude": 12, "longitude": 13, "expected_version": fetched["version"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["latitude"] == 56.1
    old_view = await api_client.get("/api/v1/map/markers", headers=headers, params={"west": 38, "south": 55, "east": 39, "north": 56})
    assert old_view.json() == []
    cleared = await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": None, "longitude": None})
    assert cleared.status_code == 200
    fetched = (await api_client.get(f"/api/v1/map/markers/{marker_id}", headers=headers)).json()
    assert fetched["latitude"] is None and fetched["longitude"] is None
    assert fetched["building_link_role"] == "represents"


@pytest.mark.asyncio
async def test_legacy_informational_marker_keeps_independent_coordinates(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    created = await api_client.post("/api/v1/map/markers", headers=headers, json=marker_payload(building_id=building["id"]))
    assert created.status_code == 201, created.text
    assert created.json()["building_link_role"] == "reference"
    house = (await api_client.get(f"/api/v1/buildings/{building['id']}", headers=headers)).json()
    assert house["latitude"] is None
    await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": 56, "longitude": 40})
    marker = (await api_client.get(f"/api/v1/map/markers/{created.json()['id']}", headers=headers)).json()
    assert marker["latitude"] == pytest.approx(55.577276)


@pytest.mark.asyncio
async def test_primary_binding_confirmation_rechecks_both_sides_and_preserves_old_point(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    first = await primary_marker(api_client, headers, building, name="Старый стиль")
    other_house = await create_building(api_client, headers, parent_id=building["address_object_id"], number="55", latitude=56, longitude=40)
    second = await primary_marker(api_client, headers, other_house, name="Новый стиль")
    patch = {"building_id": building["id"], "building_link_role": "represents", "expected_version": second["version"]}
    conflict = await api_client.patch(f"/api/v1/map/markers/{second['id']}", headers=headers, json=patch)
    assert conflict.status_code == 409, conflict.text
    detail = conflict.json()["detail"]
    assert detail["code"] == "building_binding_conflict"
    assert detail["snapshot"]["previous_marker"]["id"] == first["id"]
    assert detail["snapshot"]["previous_building"]["id"] == other_house["id"]
    # Cancellation has no writes.
    unchanged = (await api_client.get(f"/api/v1/map/markers/{first['id']}", headers=headers)).json()
    assert unchanged["version"] == first["version"]
    await api_client.patch(f"/api/v1/map/markers/{first['id']}", headers=headers, json={"name": "Изменено параллельно"})
    stale = await api_client.patch(f"/api/v1/map/markers/{second['id']}", headers=headers, json={**patch, "binding_confirmation": detail["confirmation_token"]})
    assert stale.status_code == 409
    assert stale.json()["detail"]["confirmation_token"] != detail["confirmation_token"]
    confirmed = await api_client.patch(f"/api/v1/map/markers/{second['id']}", headers=headers, json={**patch, "binding_confirmation": stale.json()["detail"]["confirmation_token"]})
    assert confirmed.status_code == 200, confirmed.text
    old = (await api_client.get(f"/api/v1/map/markers/{first['id']}", headers=headers)).json()
    assert old["building_link_role"] == "reference"
    assert old["latitude"] == pytest.approx(55.577276)
    assert confirmed.json()["latitude"] == pytest.approx(55.577276)
    repeated = await api_client.patch(f"/api/v1/map/markers/{second['id']}", headers=headers, json={"building_id": building["id"], "building_link_role": "represents"})
    assert repeated.status_code == 200


@pytest.mark.asyncio
async def test_first_binding_race_has_one_winner_and_real_unique_constraint(db_session, api_client):
    from core.map_domain import MapOperationError
    from models.users import User
    company_id, _, headers, building = await marker_building_context(db_session, api_client)
    user_id = await db_session.scalar(select(User.id).where(User.username == "admin"))
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)
    async def place(name):
        async with sessions() as session:
            try:
                return await marker_service.create_marker(session, company_id=company_id, user_id=user_id, can_manage=True,
                    data=MapMarkerCreate(**represents_payload(building, name=name, building_position={"latitude": 56, "longitude": 40})))
            except MapOperationError as exc:
                return exc.detail["code"]
    result = await asyncio.wait_for(asyncio.gather(place("Первый"), place("Второй")), timeout=10)
    assert sum(isinstance(item, str) and item == "building_binding_conflict" for item in result) == 1
    async with sessions() as session:
        markers = list((await session.scalars(select(MapMarker))).all())
        assert len(markers) == 1 and markers[0].latitude is None


@pytest.mark.asyncio
@pytest.mark.parametrize("editing", [False, True])
async def test_marker_and_explicit_building_position_roll_back_together(db_session, api_client, monkeypatch, editing):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await primary_marker(api_client, headers, building) if editing else None
    original = marker_service.set_building_position
    async def fail_position(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("simulated position failure")
    monkeypatch.setattr(marker_service, "set_building_position", fail_position)
    with pytest.raises(RuntimeError, match="simulated position failure"):
        if editing:
            await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers, json={"building_position": {"latitude": 57, "longitude": 41}})
        else:
            await api_client.post("/api/v1/map/markers", headers=headers, json=represents_payload(building, building_position={"latitude": 57, "longitude": 41}))
    house = (await api_client.get(f"/api/v1/buildings/{building['id']}", headers=headers)).json()
    assert (float(house["latitude"]) if house["latitude"] is not None else None) == (pytest.approx(55.577276) if editing else None)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["unlink", "reference", "delete", "clear_house"])
async def test_detaching_representation_preserves_point_without_moving_house(db_session, api_client, action):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    marker = await primary_marker(api_client, headers, building)
    if action == "delete":
        response = await api_client.delete(f"/api/v1/map/markers/{marker['id']}", headers=headers)
    elif action == "clear_house":
        response = await api_client.patch(f"/api/v1/buildings/{building['id']}", headers=headers, json={"latitude": None, "longitude": None})
    else:
        response = await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers,
            json={"building_id": None, "building_link_role": "none"} if action == "unlink" else {"building_link_role": "reference"})
    assert response.status_code in (200, 204), response.text
    if action not in ("delete", "clear_house"):
        assert response.json()["latitude"] == pytest.approx(55.577276)
        assert response.json()["building_link_role"] != "represents"


@pytest.mark.asyncio
async def test_legacy_sync_write_is_explicitly_rejected_without_mutation(db_session, api_client):
    _, _, headers, building = await marker_building_context(db_session, api_client)
    response = await api_client.post("/api/v1/map/markers", headers=headers, json=marker_payload(building_id=building["id"], sync_building_coordinates=True))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "legacy_coordinate_sync_removed"
    assert (await api_client.get(f"/api/v1/buildings/{building['id']}", headers=headers)).json()["latitude"] is None
