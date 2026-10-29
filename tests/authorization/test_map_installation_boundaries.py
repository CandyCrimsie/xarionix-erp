"""Real PostgreSQL regression tests: boundary edits never change cable topology."""
import asyncio

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.map_domain import MapOperationError
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from schemas.map_connections import BoundarySet
from services.map_connections import edit_installation_boundary
from test_map_connection_split import route_context, split_payload
from test_map_graph_api import reader
from test_map_routes_api import place, update_payload


async def edit(client, headers, line, vertex=1, **operation):
    return await client.patch(f"/api/v1/map/connections/{line['id']}/installation-boundaries/{vertex}", headers=headers,
        json={"expected_version": line["version"], "expected_geometry_token": line["geometry_token"], **operation})


@pytest.mark.asyncio
async def test_change_after_stops_at_next_boundary_and_persists(db_session, api_client):
    *_, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    response = await edit(api_client, headers, line, operation="set", installation_after="direct_buried")
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["geometry"] == line["geometry"]
    assert changed["installation_methods"] == ["aerial", "direct_buried", "facade"]
    assert changed["version"] == line["version"] + 1
    fresh = (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json()
    assert fresh == changed
    assert (await edit(api_client, headers, line, operation="remove", keep="previous")).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("keep,expected", [("previous", ["aerial", "aerial", "facade"]), ("next", ["duct", "duct", "facade"])])
async def test_remove_requires_explicit_merge_and_keeps_corner(db_session, api_client, keep, expected):
    *_, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    missing = await edit(api_client, headers, line, operation="remove")
    assert missing.status_code == 422
    response = await edit(api_client, headers, line, operation="remove", keep=keep)
    assert response.status_code == 200, response.text
    assert response.json()["geometry"] == line["geometry"]
    assert response.json()["installation_methods"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("index,fraction,expected", [(0, .5, ["aerial", "duct", "duct", "facade"]), (1, .5, ["aerial", "aerial", "duct", "facade"])])
async def test_move_preserves_corners_and_pass_through_anchors(db_session, api_client, index, fraction, expected):
    *_, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    attached = await place(api_client, headers, line, index=0, fraction=.25)
    line = attached["connection"]
    payload = split_payload(line, index, fraction)
    payload.pop("marker")
    response = await edit(api_client, headers, line, **{key: value for key, value in payload.items() if key not in ("expected_version", "expected_geometry_token")}, operation="move")
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["installation_methods"] == expected
    assert all(point in changed["geometry"]["coordinates"] for point in line["geometry"]["coordinates"])
    assert changed["length_m"] == pytest.approx(line["length_m"], abs=.03)
    assert changed["source"] == line["source"] and changed["target"] == line["target"]
    assert changed["route_objects"][0]["state"] == "on_route"
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MapMarker)) == 3
    # Split continues to carry both portions' segment attributes.
    split = await api_client.post(f"/api/v1/map/connections/{line['id']}/split", headers=headers, json=split_payload(changed, 1, .5))
    assert split.status_code == 201, split.text


@pytest.mark.asyncio
@pytest.mark.parametrize("index,fraction,code", [(2, .5, "boundary_order"), (1, 1, "boundary_order"), (0, 0, "near_endpoint"), (1, .99999999, "boundary_too_close")])
async def test_invalid_move_rolls_back(db_session, api_client, index, fraction, code):
    *_, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    payload = split_payload(line, index, fraction)
    payload.pop("marker")
    response = await edit(api_client, headers, line, operation="move", **{k:v for k,v in payload.items() if not k.startswith("expected_")})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == code
    assert (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json() == line


@pytest.mark.asyncio
async def test_authorization_privacy_missing_boundary_and_geometry_token(db_session, api_client):
    company, _, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    _, readonly = await reader(db_session, api_client, company, "boundary-reader")
    assert (await edit(api_client, readonly, line, operation="remove", keep="previous")).status_code == 403
    assert (await edit(api_client, {}, line, operation="remove", keep="previous")).status_code in (401, 403)
    assert (await edit(api_client, headers, line, vertex=99, operation="remove", keep="previous")).status_code == 409
    moved = await api_client.patch(f"/api/v1/map/markers/{node['id']}", headers=headers, json={"latitude":55.61,"longitude":38.28})
    assert moved.status_code == 200
    response = await edit(api_client, headers, line, operation="remove", keep="previous")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "stale_geometry"


@pytest.mark.asyncio
async def test_concurrent_edits_commit_once(db_session, api_client):
    company, _, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    factory = async_sessionmaker(db_session.bind, class_=AsyncSession, expire_on_commit=False)
    data = BoundarySet(operation="set", installation_after="indoor", expected_version=line["version"], expected_geometry_token=line["geometry_token"])
    async def run():
        async with factory() as session:
            try:
                return await edit_installation_boundary(session, company_id=company, user_id=line["owner_user_id"], can_manage=True, connection_id=line["id"], vertex_index=1, data=data)
            except MapOperationError as error:
                return error
    results = await asyncio.gather(run(), run())
    assert sum(isinstance(result, MapOperationError) for result in results) == 1
    assert next(result for result in results if isinstance(result, MapOperationError)).detail["code"] == "stale_version"


@pytest.mark.asyncio
async def test_boundary_rollback_after_flush_failure(db_session, api_client, monkeypatch):
    *_, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    original = AsyncSession.flush
    async def fail(session, *args, **kwargs):
        if any(isinstance(entity, MapConnection) and entity.version > line["version"] for entity in session.dirty):
            raise RuntimeError("injected boundary flush failure")
        return await original(session, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "flush", fail)
        with pytest.raises(RuntimeError, match="boundary flush"):
            await edit(api_client, headers, line, operation="remove", keep="next")
    assert (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json() == line


@pytest.mark.asyncio
async def test_existing_high_precision_bend_is_reused_not_rounded_into_a_sliver(db_session, api_client):
    *_, headers, building, node, line = await route_context(db_session, api_client, installation_methods=["aerial", "duct", "facade"])
    changed = await api_client.patch(f"/api/v1/map/connections/{line['id']}", headers=headers,
        json=update_payload(line, vertices=[[38.250000001, 55.580000002], [38.26, 55.585]]))
    assert changed.status_code == 200, changed.text
    line = changed.json()
    payload = split_payload(line, 0, 1)
    payload.pop("marker")
    response = await edit(api_client, headers, line, operation="move", **{k:v for k,v in payload.items() if not k.startswith("expected_")})
    assert response.status_code == 200, response.text
    assert response.json()["geometry"] == line["geometry"]
    assert response.json()["installation_methods"] == line["installation_methods"]


@pytest.mark.asyncio
async def test_other_private_owner_and_other_company_cannot_edit(db_session, api_client):
    from models.company import Company
    from models.company_memberships import CompanyMembership
    from models.membership_roles import MembershipRole
    from models.roles import Role
    from services.system_roles import sync_system_roles_for_company_in_transaction
    company, _, headers, building, node, line = await route_context(db_session, api_client, visibility="private", installation_methods=["aerial", "duct", "facade"])
    _, another = await reader(db_session, api_client, company, "boundary-other-owner")
    assert (await edit(api_client, another, line, operation="remove", keep="next")).status_code == 404
    other = Company(name="Другая компания границ", short_name="Б")
    db_session.add(other)
    await db_session.flush()
    user_id = (await api_client.get("/api/v1/auth/me", headers=headers)).json()["id"]
    membership = CompanyMembership(company_id=other.id, user_id=user_id)
    db_session.add(membership)
    await db_session.flush()
    await sync_system_roles_for_company_in_transaction(db_session, company_id=other.id)
    role_id = await db_session.scalar(select(Role.id).where(Role.company_id == other.id, Role.system_key == "administrator"))
    db_session.add(MembershipRole(company_membership_id=membership.id, role_id=role_id))
    other_id = other.id
    await db_session.commit()
    assert (await edit(api_client, {**headers, "X-Company-Id": str(other_id)}, line, operation="remove", keep="next")).status_code == 404
