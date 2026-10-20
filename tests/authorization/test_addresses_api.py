import pytest

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.scopes import PermissionScope
from core.address_normalization import normalize_address_value
from core.address_types import SYSTEM_ADDRESS_TYPES
from models.address_objects import AddressObject
from models.address_types import AddressType, AddressTypeCategory
from models.buildings import Building
from models.company_memberships import CompanyMembership
from models.entrances import Entrance
from models.equipment import Equipment
from models.locations import Location
from models.membership_roles import MembershipRole
from models.permissions import Permission
from models.role_permissions import RolePermission
from models.roles import Role
from services import addresses as address_service
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


def test_delete_conflict_classifier_accepts_dependent_data_violations():
    class DatabaseError(Exception):
        def __init__(self, sqlstate: str):
            self.sqlstate = sqlstate

    foreign_key_error = IntegrityError(
        "DELETE",
        {},
        DatabaseError("23503"),
    )
    restrict_error = IntegrityError(
        "DELETE",
        {},
        DatabaseError("23001"),
    )
    unique_error = IntegrityError(
        "DELETE",
        {},
        DatabaseError("23505"),
    )

    assert address_service._is_dependent_data_violation(foreign_key_error)
    assert address_service._is_dependent_data_violation(restrict_error)
    assert not address_service._is_dependent_data_violation(unique_error)


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

    custom = AddressType(
        code="custom_area",
        category=AddressTypeCategory.AREA,
        name="Особая зона",
        short_name="оз.",
        sort_order=75,
    )
    db_session.add(custom)
    await db_session.commit()
    await sync_system_address_types(db_session)
    await sync_system_address_types(db_session)

    result = await db_session.execute(select(AddressType))
    types = list(result.scalars().all())
    assert len(types) == len(SYSTEM_ADDRESS_TYPES) + 1
    assert next(item for item in types if item.code == "custom_area").name == "Особая зона"


@pytest.mark.asyncio
async def test_address_type_crud_generates_stable_codes_and_protects_system_types(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(db_session, api_client)
    headers = company_headers(token, company_id)

    first = await api_client.post(
        "/api/v1/address-types",
        headers=headers,
        json={
            "category": "territory",
            "name": "Гаражный кооператив",
            "short_name": "тер. ГСК",
            "sort_order": 76,
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["code"] == "custom_territory_garazhnyi_kooperativ"
    assert first.json()["is_system"] is False

    second = await api_client.post(
        "/api/v1/address-types",
        headers=headers,
        json={
            "category": "territory",
            "name": "Гаражный кооператив",
            "short_name": "тер. ГСК-2",
            "sort_order": 77,
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["code"] == "custom_territory_garazhnyi_kooperativ_2"

    updated = await api_client.patch(
        f"/api/v1/address-types/{first.json()['id']}",
        headers=headers,
        json={"name": "Гаражная территория", "sort_order": 75},
    )
    assert updated.status_code == 200
    assert updated.json()["code"] == first.json()["code"]

    system_update = await api_client.patch(
        f"/api/v1/address-types/{types['city']}",
        headers=headers,
        json={"name": "Город изменённый"},
    )
    system_delete = await api_client.delete(
        f"/api/v1/address-types/{types['city']}",
        headers=headers,
    )
    assert system_update.status_code == 409
    assert system_delete.status_code == 409

    custom_type = first.json()
    city = await create_object(
        api_client,
        headers,
        type_id=types["city"],
        name="Жуковский",
    )
    await create_object(
        api_client,
        headers,
        type_id=custom_type["id"],
        name="ГСК Метеор",
        parent_id=city["id"],
    )
    in_use_delete = await api_client.delete(
        f"/api/v1/address-types/{custom_type['id']}",
        headers=headers,
    )
    assert in_use_delete.status_code == 409

    unused_delete = await api_client.delete(
        f"/api/v1/address-types/{second.json()['id']}",
        headers=headers,
    )
    assert unused_delete.status_code == 204


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
async def test_refined_hierarchy_rejects_locality_nesting_and_preserves_legacy_edits(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city = await create_object(
        api_client,
        headers,
        type_id=types["city"],
        name="Москва",
    )

    nested_city = await api_client.post(
        "/api/v1/address-objects",
        headers=headers,
        json={
            "parent_id": city["id"],
            "type_id": types["city"],
            "name": "Зеленоград",
        },
    )
    nested_settlement = await api_client.post(
        "/api/v1/address-objects",
        headers=headers,
        json={
            "parent_id": city["id"],
            "type_id": types["settlement"],
            "name": "Посёлок внутри города",
        },
    )
    assert nested_city.status_code == 409
    assert nested_settlement.status_code == 409

    # Historical rows remain readable and can still be renamed. Only a real
    # hierarchy/type transition is checked against the refined rules.
    legacy = AddressObject(
        parent_id=city["id"],
        type_id=types["settlement"],
        name="Старое название",
        normalized_name=normalize_address_value("Старое название"),
    )
    db_session.add(legacy)
    await db_session.commit()
    rename = await api_client.patch(
        f"/api/v1/address-objects/{legacy.id}",
        headers=headers,
        json={"name": "Новое название", "type_id": types["settlement"]},
    )
    assert rename.status_code == 200, rename.text
    assert rename.json()["name"] == "Новое название"


@pytest.mark.asyncio
async def test_territory_accepts_direct_buildings_and_optional_streets(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city = await create_object(
        api_client,
        headers,
        type_id=types["city"],
        name="Жуковский",
    )
    territory = await create_object(
        api_client,
        headers,
        type_id=types["snt_territory"],
        name="Облепиха",
        parent_id=city["id"],
    )

    direct_building = await create_building_request(
        api_client,
        headers,
        territory["id"],
        number="41",
    )
    assert direct_building.status_code == 201, direct_building.text
    assert direct_building.json()["full_address"] == (
        "Жуковский, тер. СНТ Облепиха, д. 41"
    )

    street = await create_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Центральная",
        parent_id=territory["id"],
    )
    street_building = await create_building_request(
        api_client,
        headers,
        street["id"],
        number="42",
    )
    assert street_building.status_code == 201

    district = await create_object(
        api_client,
        headers,
        type_id=types["district"],
        name="Центральный",
        parent_id=city["id"],
    )
    invalid_area_building = await create_building_request(
        api_client,
        headers,
        district["id"],
        number="1",
    )
    assert invalid_area_building.status_code == 409


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
async def test_smart_address_search_uses_postgresql_matching_and_ranking(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    company_id, token, types = await initialize_address_context(
        db_session, api_client
    )
    headers = company_headers(token, company_id)

    _, ramenskoe_gagarina = await create_standard_path(
        api_client,
        headers,
        types,
        city_name="Раменское",
        street_name="Гагарина",
    )
    _, ramenskoe_typo_street = await create_standard_path(
        api_client,
        headers,
        types,
        city_name="Жуковский",
        street_name="Гагарена",
    )
    _, moscow_gagarina = await create_standard_path(
        api_client,
        headers,
        types,
        city_name="Москва",
        street_name="Гагарина",
    )
    moscow = moscow_gagarina["parent_id"]
    moscow_lenina = await create_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Ленина",
        parent_id=moscow,
    )
    _, orel_elochnaya = await create_standard_path(
        api_client,
        headers,
        types,
        city_name="Орёл",
        street_name="Ёлочная",
    )

    async def create(street_id: int, number: str, **parts: str) -> dict:
        response = await create_building_request(
            api_client,
            headers,
            street_id,
            number=number,
            corpus=parts.get("corpus"),
            structure=parts.get("structure"),
        )
        assert response.status_code == 201, response.text
        return response.json()

    ram_51 = await create(ramenskoe_gagarina["id"], "51")
    ram_53 = await create(ramenskoe_gagarina["id"], "53")
    ram_53_corpus = await create(ramenskoe_gagarina["id"], "53", corpus="2")
    ram_53_structure = await create(
        ramenskoe_gagarina["id"], "53", structure="2"
    )
    await create(ramenskoe_gagarina["id"], "153")
    typo_53 = await create(ramenskoe_typo_street["id"], "53")
    moscow_53 = await create(moscow_gagarina["id"], "53")
    moscow_15 = await create(moscow_lenina["id"], "15")
    orel_1 = await create(orel_elochnaya["id"], "1")

    async def search(query: str, *, limit: int = 20, offset: int = 0) -> dict:
        response = await api_client.get(
            "/api/v1/addresses/search",
            headers=headers,
            params={"q": query, "limit": limit, "offset": offset},
        )
        assert response.status_code == 200, response.text
        return response.json()

    for query in (
        "рам гагар 53",
        "раменское гагарина 53",
        "гагар 53 рам",
        "Раменское, ул. Гагарина, д. 53",
        "ГАгарИНА 53 РАМЕНСКОЕ",
        "Гагарина,    53 Раменское",
    ):
        result = await search(query)
        assert [item["id"] for item in result["items"][:2]] == [
            ram_53["id"],
            ram_53_corpus["id"],
        ]
        assert all(item["number"] == "53" for item in result["items"])

    for query in ("рам гагар 53 корп 2", "рам гагар 53 к2"):
        result = await search(query)
        assert [item["id"] for item in result["items"]] == [
            ram_53_corpus["id"]
        ]

    structure_result = await search(
        "раменское гагарина 53 строение 2"
    )
    assert [item["id"] for item in structure_result["items"]] == [
        ram_53_structure["id"]
    ]

    street_result = await search("рам гагар")
    assert street_result["total"] == 5
    assert {item["id"] for item in street_result["items"]} >= {
        ram_51["id"],
        ram_53["id"],
    }

    cross_city = await search("гагарина 53")
    assert {ram_53["id"], moscow_53["id"]}.issubset(
        {item["id"] for item in cross_city["items"]}
    )
    assert all(item["number"] == "53" for item in cross_city["items"])

    fuzzy = await search("раменское гагарена 53")
    assert fuzzy["items"][0]["id"] == ram_53["id"]

    exact_before_fuzzy = await search("гагарина 53")
    exact_ids = [item["id"] for item in exact_before_fuzzy["items"]]
    assert exact_ids.index(ram_53["id"]) < exact_ids.index(typo_53["id"])

    lenina = await search("мос лен 15")
    assert [item["id"] for item in lenina["items"]] == [moscow_15["id"]]

    yo_result = await search("орел елоч 1")
    assert [item["id"] for item in yo_result["items"]] == [orel_1["id"]]

    first_page = await search("гагар 53", limit=2)
    second_page = await search("гагар 53", limit=2, offset=2)
    repeated_first_page = await search("гагар 53", limit=2)
    assert first_page["total"] == 5
    assert first_page["limit"] == 2
    assert first_page["offset"] == 0
    assert second_page["offset"] == 2
    assert first_page["items"] == repeated_first_page["items"]
    assert not (
        {item["id"] for item in first_page["items"]}
        & {item["id"] for item in second_page["items"]}
    )

    injection = await search("'; DROP TABLE buildings; --")
    assert injection["items"] == []
    still_available = await search("мос лен 15")
    assert still_available["items"][0]["id"] == moscow_15["id"]
    assert "company_id" not in still_available["items"][0]
    assert "locations" not in still_available["items"][0]

    too_many_tokens = await api_client.get(
        "/api/v1/addresses/search",
        headers=headers,
        params={"q": " ".join(f"слово{index}" for index in range(13))},
    )
    assert too_many_tokens.status_code == 422


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
async def test_delete_endpoints_map_concurrent_fk_conflicts_to_http_409(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
    monkeypatch: pytest.MonkeyPatch,
):
    company_id, token, types = await initialize_address_context(db_session, api_client)
    headers = company_headers(token, company_id)
    city, street = await create_standard_path(api_client, headers, types)
    leaf_street = await create_object(
        api_client,
        headers,
        type_id=types["street"],
        name="Гагарина",
        parent_id=city["id"],
    )
    empty_building = (
        await create_building_request(
            api_client,
            headers,
            street["id"],
            number="17",
        )
    ).json()
    occupied_building = (
        await create_building_request(
            api_client,
            headers,
            street["id"],
            number="19",
        )
    ).json()
    empty_entrance = (
        await api_client.post(
            f"/api/v1/buildings/{occupied_building['id']}/entrances",
            headers=headers,
            json={"number": "1"},
        )
    ).json()
    empty_location = (
        await api_client.post(
            "/api/v1/locations",
            headers=headers,
            json={
                "building_id": occupied_building["id"],
                "entrance_id": None,
                "floor": "-1",
                "name": "Серверная",
            },
        )
    ).json()

    async def add_building_after_check(
        session: AsyncSession,
        address_object_id: int,
    ) -> bool:
        session.add(
            Building(
                address_object_id=address_object_id,
                number="99",
                normalized_number="99",
                normalized_corpus="",
                normalized_structure="",
            )
        )
        await session.flush()
        return False

    monkeypatch.setattr(
        address_service,
        "address_object_has_children_or_buildings",
        add_building_after_check,
    )
    address_delete = await api_client.delete(
        f"/api/v1/address-objects/{leaf_street['id']}",
        headers=headers,
    )
    assert address_delete.status_code == 409
    assert address_delete.json()["detail"] == "Address record has dependent data"

    async def add_entrance_after_check(
        session: AsyncSession,
        building_id: int,
    ) -> bool:
        session.add(
            Entrance(
                building_id=building_id,
                number="race",
                normalized_number="race",
            )
        )
        await session.flush()
        return False

    monkeypatch.setattr(
        address_service,
        "building_has_entrances_or_locations",
        add_entrance_after_check,
    )
    building_delete = await api_client.delete(
        f"/api/v1/buildings/{empty_building['id']}",
        headers=headers,
    )
    assert building_delete.status_code == 409
    assert building_delete.json()["detail"] == "Address record has dependent data"

    async def add_location_after_check(
        session: AsyncSession,
        entrance_id: int,
    ) -> bool:
        entrance = await session.get(Entrance, entrance_id)
        assert entrance is not None
        session.add(
            Location(
                company_id=company_id,
                building_id=entrance.building_id,
                entrance_id=entrance_id,
                floor="1",
                name="Race location",
            )
        )
        await session.flush()
        return False

    monkeypatch.setattr(
        address_service,
        "entrance_has_locations",
        add_location_after_check,
    )
    entrance_delete = await api_client.delete(
        f"/api/v1/entrances/{empty_entrance['id']}",
        headers=headers,
    )
    assert entrance_delete.status_code == 409
    assert entrance_delete.json()["detail"] == "Address record has dependent data"

    async def add_equipment_after_check(
        session: AsyncSession,
        location_id: int,
    ) -> bool:
        session.add(Equipment(location_id=location_id, name="Race equipment"))
        await session.flush()
        return False

    monkeypatch.setattr(
        address_service,
        "location_has_equipment",
        add_equipment_after_check,
    )
    location_delete = await api_client.delete(
        f"/api/v1/locations/{empty_location['id']}",
        headers=headers,
    )
    assert location_delete.status_code == 409
    assert location_delete.json()["detail"] == "Address record has dependent data"


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

    catalog_b = await api_client.get(
        "/api/v1/address-objects",
        headers=headers_b,
    )
    assert catalog_b.status_code == 200
    assert [item["id"] for item in catalog_b.json()] == [
        street["parent_id"]
    ]

    global_update = await api_client.patch(
        f"/api/v1/address-objects/{street['id']}",
        headers=headers_b,
        json={"name": "Ленина Общая"},
    )
    assert global_update.status_code == 200
    catalog_a = await api_client.get(
        f"/api/v1/address-objects/{street['id']}",
        headers=headers_a,
    )
    assert catalog_a.status_code == 200
    assert catalog_a.json()["name"] == "Ленина Общая"

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
    assert (
        await api_client.get(
            "/api/v1/addresses/search",
            headers=reader_headers,
            params={"q": "Москва"},
        )
    ).status_code == 200
    denied = await api_client.post(
        "/api/v1/address-objects",
        headers=reader_headers,
        json={"parent_id": None, "type_id": types["city"], "name": "Москва"},
    )
    assert denied.status_code == 403
    denied_type_management = await api_client.post(
        "/api/v1/address-types",
        headers=reader_headers,
        json={
            "category": "territory",
            "name": "Закрытая территория",
            "short_name": "тер.",
            "sort_order": 75,
        },
    )
    assert denied_type_management.status_code == 403

    user_without_access = await register_user(
        db_session,
        username="address-no-access",
        password="password123",
    )
    db_session.add(
        CompanyMembership(
            user_id=user_without_access.id,
            company_id=company_id,
        )
    )
    await db_session.commit()
    no_access_login = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "address-no-access", "password": "password123"},
    )
    no_access_headers = company_headers(
        no_access_login.json()["access_token"],
        company_id,
    )
    denied_search = await api_client.get(
        "/api/v1/addresses/search",
        headers=no_access_headers,
        params={"q": "Москва"},
    )
    assert denied_search.status_code == 403

    no_context = await api_client.get(
        "/api/v1/address-objects",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert no_context.status_code == 400
