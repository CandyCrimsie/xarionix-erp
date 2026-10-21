import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import config
from models.company_memberships import CompanyMembership
from services.address_types import sync_system_address_types
from services.auth import register_user


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
