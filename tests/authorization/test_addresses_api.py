import pytest

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.scopes import PermissionScope
from models.company_memberships import CompanyMembership
from models.membership_roles import MembershipRole
from models.permissions import Permission
from models.role_permissions import RolePermission
from models.roles import Role
from services.address_types import sync_system_address_types
from services.auth import register_user


async def initialize_address_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
) -> tuple[int, str, dict[str, int]]:
    await sync_system_address_types(db_session)
    setup = await api_client.post(
        "/api/v1/setup/initialize",
        json={
            "company": {
                "name": "Address Company",
                "short_name": "ADDR",
            },
        },
    )
    assert setup.status_code == 201
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "password123"},
    )
    assert login.status_code == 200
    company_id = setup.json()["company_id"]
    token = login.json()["access_token"]
    response = await api_client.get(
        "/api/v1/address-types",
        headers=company_headers(token, company_id),
    )
    assert response.status_code == 200
    type_ids = {item["code"]: item["id"] for item in response.json()}
    return company_id, token, type_ids


def company_headers(token: str, company_id: int) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": str(company_id),
    }


async def create_object(
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


async def create_standard_path(
    api_client: AsyncClient,
    headers: dict[str, str],
    type_ids: dict[str, int],
    *,
    city_name: str = "Москва",
    street_name: str = "Ленина",
) -> tuple[dict, dict]:
    city = await create_object(
        api_client,
        headers,
        type_id=type_ids["city"],
        name=city_name,
    )
    street = await create_object(
        api_client,
        headers,
        type_id=type_ids["street"],
        name=street_name,
        parent_id=city["id"],
    )
    return city, street


async def create_building_request(
    api_client: AsyncClient,
    headers: dict[str, str],
    street_id: int,
    *,
    number: str,
    corpus: str | None = None,
    structure: str | None = None,
) -> object:
    return await api_client.post(
        f"/api/v1/address-objects/{street_id}/buildings",
        headers=headers,
        json={
            "address_object_id": street_id,
            "number": number,
            "corpus": corpus,
            "structure": structure,
            "latitude": None,
            "longitude": None,
        },
    )


@pytest.mark.asyncio
async def test_address_type_bootstrap_is_idempotent_and_preserves_custom_types(
    db_session: AsyncSession,
):
    await sync_system_address_types(db_session)
    first = list((await db_session.execute(select(Permission))).scalars().all())
    assert first == []

    from models.address_types import AddressType, AddressTypeCategory

    custom = AddressType(
        code="microdistrict",
        category=AddressTypeCategory.AREA,
        name="Микрорайон",
        short_name="мкр.",
        sort_order=75,
    )
    db_session.add(custom)
    await db_session.commit()
    await sync_system_address_types(db_session)
    await sync_system_address_types(db_session)

    result = await db_session.execute(select(AddressType))
    types = list(result.scalars().all())
    assert len(types) == 11
    assert next(item for item in types if item.code == "microdistrict").name == "Микрорайон"


@pytest.mark.asyncio
async def test_address_hierarchy_supports_optional_area_and_rejects_invalid_moves(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(
        db_session, api_client
    )
    headers = company_headers(token, company_id)
    city = await create_object(
        api_client,
        headers,
        type_id=types["city"],
        name="  Москва   ",
    )
    district = await create_object(
        api_client,
        headers,
        type_id=types["district"],
        name="Академический район",
        parent_id=city["id"],
    )
    street_under_area = await create_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Дмитрия Ульянова",
        parent_id=district["id"],
    )
    street_under_city = await create_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Ленина",
        parent_id=city["id"],
    )
    assert city["name"] == "Москва"
    assert street_under_area["parent_id"] == district["id"]
    assert street_under_city["parent_id"] == city["id"]

    duplicate = await api_client.post(
        "/api/v1/address-objects",
        headers=headers,
        json={
            "parent_id": city["id"],
            "type_id": types["street"],
            "name": "  ЛЕНИНА ",
        },
    )
    assert duplicate.status_code == 409

    invalid_root = await api_client.post(
        "/api/v1/address-objects",
        headers=headers,
        json={"parent_id": None, "type_id": types["street"], "name": "Тверская"},
    )
    assert invalid_root.status_code == 409

    self_parent = await api_client.patch(
        f"/api/v1/address-objects/{city['id']}",
        headers=headers,
        json={"parent_id": city["id"]},
    )
    assert self_parent.status_code == 409

    cycle = await api_client.patch(
        f"/api/v1/address-objects/{city['id']}",
        headers=headers,
        json={"parent_id": street_under_area["id"]},
    )
    assert cycle.status_code == 409

    tree = await api_client.get("/api/v1/address-objects/tree", headers=headers)
    assert tree.status_code == 200
    assert tree.json()[0]["children"][0]["children"][0]["name"] == "Дмитрия Ульянова"


@pytest.mark.asyncio
async def test_building_uniqueness_coordinates_and_full_address_search(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(db_session, api_client)
    headers = company_headers(token, company_id)
    _, moscow_street = await create_standard_path(
        api_client, headers, types, city_name="Москва", street_name="Ленина"
    )
    _, ramenskoe_street = await create_standard_path(
        api_client, headers, types, city_name="Раменское", street_name="Ленина"
    )

    first = await create_building_request(
        api_client, headers, moscow_street["id"], number=" 15 "
    )
    assert first.status_code == 201, first.text
    assert first.json()["full_address"] == "Москва, ул. Ленина, д. 15"

    duplicate = await create_building_request(
        api_client, headers, moscow_street["id"], number="15"
    )
    assert duplicate.status_code == 409

    corpus = await create_building_request(
        api_client,
        headers,
        moscow_street["id"],
        number="15",
        corpus="2",
    )
    assert corpus.status_code == 201

    other_city = await create_building_request(
        api_client, headers, ramenskoe_street["id"], number="15"
    )
    assert other_city.status_code == 201

    invalid_coordinates = await api_client.post(
        f"/api/v1/address-objects/{moscow_street['id']}/buildings",
        headers=headers,
        json={
            "address_object_id": moscow_street["id"],
            "number": "17",
            "latitude": 91,
            "longitude": 37,
        },
    )
    assert invalid_coordinates.status_code == 422

    search = await api_client.get(
        "/api/v1/addresses/search",
        headers=headers,
        params={"q": "Ленина 15", "limit": 20, "offset": 0},
    )
    assert search.status_code == 200, search.text
    assert search.json()["total"] == 3
    assert {
        item["full_address"] for item in search.json()["items"]
    } == {
        "Москва, ул. Ленина, д. 15",
        "Москва, ул. Ленина, д. 15, корп. 2",
        "Раменское, ул. Ленина, д. 15",
    }

    narrowed = await api_client.get(
        "/api/v1/addresses/search",
        headers=headers,
        params={"q": "Москва Ленина 15 корпус 2"},
    )
    assert narrowed.status_code == 200
    assert [item["id"] for item in narrowed.json()["items"]] == [corpus.json()["id"]]


@pytest.mark.asyncio
async def test_entrances_locations_integrity_and_safe_deletion(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city, street = await create_standard_path(api_client, headers, types)
    building_one_response = await create_building_request(
        api_client, headers, street["id"], number="15"
    )
    building_two_response = await create_building_request(
        api_client, headers, street["id"], number="17"
    )
    building_one = building_one_response.json()
    building_two = building_two_response.json()

    entrance_one = await api_client.post(
        f"/api/v1/buildings/{building_one['id']}/entrances",
        headers=headers,
        json={"number": "1"},
    )
    assert entrance_one.status_code == 201
    duplicate = await api_client.post(
        f"/api/v1/buildings/{building_one['id']}/entrances",
        headers=headers,
        json={"number": " 1 "},
    )
    assert duplicate.status_code == 409
    entrance_other_building = await api_client.post(
        f"/api/v1/buildings/{building_two['id']}/entrances",
        headers=headers,
        json={"number": "1"},
    )
    assert entrance_other_building.status_code == 201

    mismatch = await api_client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "building_id": building_one["id"],
            "entrance_id": entrance_other_building.json()["id"],
            "floor": "9",
            "name": "Технический шкаф",
        },
    )
    assert mismatch.status_code == 409

    inside_entrance = await api_client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "building_id": building_one["id"],
            "entrance_id": entrance_one.json()["id"],
            "floor": "9",
            "name": "Технический шкаф",
            "description": "Возле лифтовой шахты",
        },
    )
    without_entrance = await api_client.post(
        "/api/v1/locations",
        headers=headers,
        json={
            "building_id": building_one["id"],
            "entrance_id": None,
            "floor": "-1",
            "name": "Подвал",
        },
    )
    assert inside_entrance.status_code == 201
    assert without_entrance.status_code == 201

    assert (
        await api_client.delete(
            f"/api/v1/entrances/{entrance_one.json()['id']}", headers=headers
        )
    ).status_code == 409
    assert (
        await api_client.delete(
            f"/api/v1/buildings/{building_one['id']}", headers=headers
        )
    ).status_code == 409
    assert (
        await api_client.delete(
            f"/api/v1/address-objects/{city['id']}", headers=headers
        )
    ).status_code == 409


@pytest.mark.asyncio
async def test_locations_are_isolated_by_company_context(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_a, token, types = await initialize_address_context(db_session, api_client)
    headers_a = company_headers(token, company_a)
    _, street = await create_standard_path(api_client, headers_a, types)
    building = (
        await create_building_request(api_client, headers_a, street["id"], number="15")
    ).json()
    location = await api_client.post(
        "/api/v1/locations",
        headers=headers_a,
        json={
            "building_id": building["id"],
            "entrance_id": None,
            "floor": "-1",
            "name": "Серверная A",
            "description": "Секретный комментарий A",
        },
    )
    assert location.status_code == 201

    company_b_response = await api_client.post(
        "/api/v1/companies",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Company B", "short_name": "B"},
    )
    assert company_b_response.status_code == 201, company_b_response.text
    company_b = company_b_response.json()["id"]
    headers_b = company_headers(token, company_b)

    list_b = await api_client.get(
        f"/api/v1/buildings/{building['id']}/locations",
        headers=headers_b,
    )
    assert list_b.status_code == 200
    assert list_b.json() == []
    update_from_b = await api_client.patch(
        f"/api/v1/locations/{location.json()['id']}",
        headers=headers_b,
        json={"name": "Compromised"},
    )
    assert update_from_b.status_code == 404


@pytest.mark.asyncio
async def test_address_permissions_enforce_read_and_manage(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, admin_token, types = await initialize_address_context(
        db_session, api_client
    )
    user = await register_user(
        db_session,
        username="address-reader",
        password="password123",
    )
    membership = CompanyMembership(user_id=user.id, company_id=company_id)
    db_session.add(membership)
    await db_session.flush()
    permission = (
        await db_session.execute(
            select(Permission).where(Permission.code == "addresses.read")
        )
    ).scalar_one()
    role = Role(company_id=company_id, name="Address Reader")
    db_session.add(role)
    await db_session.flush()
    db_session.add_all(
        [
            RolePermission(
                role_id=role.id,
                permission_id=permission.id,
                scope=PermissionScope.COMPANY,
            ),
            MembershipRole(company_membership_id=membership.id, role_id=role.id),
        ]
    )
    await db_session.commit()
    login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "address-reader", "password": "password123"},
    )
    reader_headers = company_headers(login.json()["access_token"], company_id)

    assert (
        await api_client.get("/api/v1/address-objects", headers=reader_headers)
    ).status_code == 200
    denied = await api_client.post(
        "/api/v1/address-objects",
        headers=reader_headers,
        json={"parent_id": None, "type_id": types["city"], "name": "Москва"},
    )
    assert denied.status_code == 403

    no_context = await api_client.get(
        "/api/v1/address-objects",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert no_context.status_code == 400
