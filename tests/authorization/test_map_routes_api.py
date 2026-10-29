import asyncio

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.exc import IntegrityError

from core.map_domain import MapOperationError
from models.map_connections import MapConnection
from models.map_markers import MapMarker
from models.map_route_objects import MapRouteObject
from test_map_connection_split import route_context, split_payload
from test_map_graph_api import point, reader


async def place(client, headers, line, point_type="chamber", index=1, fraction=.37, **extra):
    payload = split_payload(line, index, fraction)
    payload["marker"].update(point_type=point_type, icon_name={"fiber_box":"fiber-box"}.get(point_type,point_type), name="Объект трассы")
    payload.update(extra)
    response=await client.post(f"/api/v1/map/connections/{line['id']}/route-objects",headers=headers,json=payload)
    assert response.status_code==201,response.text
    return response.json()


def update_payload(line, **overrides):
    values={key:line[key] for key in ("name","description","visibility","medium","status","fiber_count","category","vertices","installation_methods")}
    values.update(source={key:line["source"][key] for key in ("kind","id")},target={key:line["target"][key] for key in ("kind","id")},expected_version=line["version"])
    return {**values,**overrides}


@pytest.mark.asyncio
@pytest.mark.parametrize("point_type",["fiber_box","odf","transition"])
async def test_new_types_and_legacy_icons(db_session,api_client,point_type):
    _,_,headers,*_=await route_context(db_session,api_client)
    marker=await point(api_client,headers,point_type=point_type,visibility="company",icon_name="fiber-box" if point_type=="fiber_box" else point_type)
    assert marker["point_type"]==point_type
    legacy=await point(api_client,headers,point_type="note",visibility="private",icon_name="server")
    assert legacy["icon_name"]=="server"


@pytest.mark.asyncio
@pytest.mark.parametrize("point_type",["splice","fiber_box","odf","network_node","cabinet"])
async def test_generalized_split_preserves_mixed_methods(db_session,api_client,point_type):
    _,_,headers,_,_,line=await route_context(db_session,api_client,installation_methods=["aerial","duct","facade"])
    payload=split_payload(line)
    payload["marker"]["point_type"]=point_type
    response=await api_client.post(f"/api/v1/map/connections/{line['id']}/split",headers=headers,json=payload)
    assert response.status_code==201,response.text
    result=response.json()
    assert result["marker"]["point_type"]==point_type
    first,second=result["connections"]
    assert first["installation_methods"]==["aerial","duct"]
    assert second["installation_methods"]==["duct","facade"]


@pytest.mark.asyncio
async def test_pass_through_does_not_split_and_requires_explicit_detach(db_session,api_client):
    _,_,headers,_,_,line=await route_context(db_session,api_client)
    result=await place(api_client,headers,line)
    marker,changed=result["marker"],result["connection"]
    assert marker["point_type"]=="chamber" and marker["route_attachment"]["connection_id"]==line["id"]
    assert changed["geometry"]==line["geometry"] and changed["source"]==line["source"] and changed["target"]==line["target"]
    assert changed["version"]==line["version"]+1 and len(changed["route_objects"])==1
    assert changed["route_objects"][0]["state"]=="on_route"
    assert await db_session.scalar(select(func.count()).select_from(MapConnection))==1
    moved=await api_client.patch(f"/api/v1/map/markers/{marker['id']}",headers=headers,json={"latitude":55.8,"longitude":38.9})
    assert moved.status_code==409
    denied=await api_client.delete(f"/api/v1/map/connections/{line['id']}",headers=headers)
    assert denied.status_code==409 and denied.json()["detail"]["code"]=="route_has_objects"
    detached=await api_client.post(f"/api/v1/map/connections/{line['id']}/route-objects/{marker['id']}/detach",headers=headers,json={"expected_version":changed["version"],"expected_geometry_token":changed["geometry_token"]})
    assert detached.status_code==200,detached.text
    assert detached.json()["marker"]["route_attachment"] is None
    assert detached.json()["marker"]["latitude"]==marker["latitude"]
    assert (await api_client.delete(f"/api/v1/map/connections/{line['id']}",headers=headers)).status_code==204
    assert (await api_client.get(f"/api/v1/map/markers/{marker['id']}",headers=headers)).status_code==200


@pytest.mark.asyncio
async def test_boundary_without_marker_and_transition_with_boundary(db_session,api_client):
    _,_,headers,_,_,line=await route_context(db_session,api_client,installation_methods=["aerial"]*3)
    payload=split_payload(line)
    payload.pop("marker")
    response=await api_client.post(f"/api/v1/map/connections/{line['id']}/installation-boundaries",headers=headers,json={**payload,"installation_after":"duct","until":"end"})
    assert response.status_code==200,response.text
    changed=response.json()
    assert changed["installation_methods"]==["aerial","aerial","duct","duct"]
    assert len(changed["vertices"])==len(line["vertices"])+1
    assert await db_session.scalar(select(func.count()).select_from(MapConnection))==1
    assert await db_session.scalar(select(func.count()).select_from(MapRouteObject))==0
    result=await place(api_client,headers,changed,"transition",index=2,fraction=.5,installation_after="direct_buried")
    assert result["connection"]["installation_methods"]==["aerial","aerial","duct","direct_buried","direct_buried"]
    assert result["marker"]["point_type"]=="transition"


@pytest.mark.asyncio
async def test_split_reassigns_objects_without_moving_or_connecting_them(db_session,api_client):
    _,_,headers,_,_,line=await route_context(db_session,api_client)
    before=await place(api_client,headers,line,"pole",index=0,fraction=.5)
    after=await place(api_client,headers,before["connection"],"chamber",index=2,fraction=.5)
    response=await api_client.post(f"/api/v1/map/connections/{line['id']}/split",headers=headers,json=split_payload(after["connection"],1,.6))
    assert response.status_code==201,response.text
    first,second=response.json()["connections"]
    assert [item["marker_id"] for item in first["route_objects"]]==[before["marker"]["id"]]
    assert [item["marker_id"] for item in second["route_objects"]]==[after["marker"]["id"]]
    assert all(item["state"]=="on_route" for route in (first,second) for item in route["route_objects"])
    moved=(await api_client.get(f"/api/v1/map/markers/{after['marker']['id']}",headers=headers)).json()
    assert moved["latitude"]==after["marker"]["latitude"] and moved["longitude"]==after["marker"]["longitude"]
    assert moved["route_attachment"]["connection_id"]==second["id"]
    assert first["target"]["id"]!=before["marker"]["id"] and second["source"]["id"]!=after["marker"]["id"]


@pytest.mark.asyncio
async def test_fixed_anchor_guards_route_and_live_endpoint_changes(db_session,api_client):
    _,_,headers,building,node,line=await route_context(db_session,api_client)
    result=await place(api_client,headers,line,index=0,fraction=.5)
    changed=result["connection"]
    moved=await api_client.patch(f"/api/v1/buildings/{building['id']}",headers=headers,json={"latitude":55.8,"longitude":38.9})
    assert moved.status_code==409,moved.text
    # Moving the other endpoint doesn't change the first segment's fixed anchor.
    assert (await api_client.patch(f"/api/v1/map/markers/{node['id']}",headers=headers,json={"latitude":55.61,"longitude":38.28})).status_code==200
    bad=await api_client.patch(f"/api/v1/map/connections/{line['id']}",headers=headers,json=update_payload(changed,vertices=[[39,56],[39.1,56.1]]))
    assert bad.status_code==409,bad.text
    fresh=(await api_client.get(f"/api/v1/map/connections/{line['id']}",headers=headers)).json()
    # Subdivision preserves a geographical anchor, not an eternal segment index.
    anchor=[result["marker"]["longitude"],result["marker"]["latitude"]]
    valid=await api_client.patch(f"/api/v1/map/connections/{line['id']}",headers=headers,json=update_payload(fresh,vertices=[anchor,*fresh["vertices"]],installation_methods=["unknown"]*4))
    assert valid.status_code==200,valid.text
    assert valid.json()["route_objects"][0]["state"]=="on_route"


@pytest.mark.asyncio
async def test_known_methods_are_not_silently_dropped_by_old_clients(db_session,api_client):
    _,_,headers,_,_,line=await route_context(db_session,api_client,installation_methods=["aerial","duct","indoor"])
    payload=update_payload(line,vertices=[[38.251,55.581],[38.261,55.586]])
    payload.pop("installation_methods")
    response=await api_client.patch(f"/api/v1/map/connections/{line['id']}",headers=headers,json=payload)
    assert response.status_code==409 and response.json()["detail"]["code"]=="installation_methods_required"
    for invalid in (["duct"], ["space"]*3):
        bad=await api_client.patch(f"/api/v1/map/connections/{line['id']}",headers=headers,json=update_payload(line,installation_methods=invalid))
        assert bad.status_code==422


@pytest.mark.asyncio
async def test_operations_keep_rbac_versions_and_server_owned_topology(db_session,api_client):
    company,_,headers,_,_,line=await route_context(db_session,api_client)
    _,readonly=await reader(db_session,api_client,company,"route-reader")
    payload=split_payload(line)
    payload["marker"]["point_type"]="chamber"
    for path in ("route-objects","split"):
        denied=await api_client.post(f"/api/v1/map/connections/{line['id']}/{path}",headers=readonly,json=payload)
        assert denied.status_code in (403,422)
    forged=await api_client.post(f"/api/v1/map/connections/{line['id']}/route-objects",headers=headers,json={**payload,"owner_user_id":1})
    assert forged.status_code==422
    assert (await api_client.post(f"/api/v1/map/connections/{line['id']}/split",headers=headers,json=payload)).status_code==422
    first=await place(api_client,headers,line)
    repeated=await api_client.post(f"/api/v1/map/connections/{line['id']}/route-objects",headers=headers,json=payload)
    assert repeated.status_code==409 and repeated.json()["detail"]["code"]=="stale_version"


@pytest.mark.asyncio
async def test_upgrade_preserves_existing_records_and_is_idempotent(db_session,api_client):
    _,_,headers,_,_,line=await route_context(db_session,api_client)
    connection=await db_session.connection()
    # Reproduce the actual pre-workspace schema, not a hybrid with newer FKs.
    await connection.execute(text("DROP TABLE map_passports, map_preferences, map_layer_members, map_layers"))
    await connection.execute(text("DROP TABLE map_route_objects"))
    await connection.execute(text("ALTER TABLE map_connections DROP CONSTRAINT ck_map_connections_installation, DROP CONSTRAINT uq_map_connections_company_id, DROP COLUMN installation_methods"))
    await connection.execute(text("ALTER TABLE map_markers DROP CONSTRAINT ck_map_markers_point_type"))
    await connection.execute(text("ALTER TABLE map_markers ADD CONSTRAINT ck_map_markers_point_type CHECK(point_type IN ('building','network_node','cabinet','splice','pole','chamber','equipment','note'))"))
    from database.map_routes_upgrade import inspect_route_schema,upgrade_route_schema
    assert (await inspect_route_schema(connection))["upgrade_required"] is True
    assert (await upgrade_route_schema(connection))["upgrade_required"] is True
    assert (await upgrade_route_schema(connection))["upgrade_required"] is False
    from database.map_workspace_upgrade import upgrade_workspace_schema
    await upgrade_workspace_schema(connection)
    await db_session.commit()
    fresh=(await api_client.get(f"/api/v1/map/connections/{line['id']}",headers=headers)).json()
    assert fresh["geometry"]==line["geometry"] and fresh["installation_methods"]==["unknown"]*3
    marker=await point(api_client,headers,point_type="fiber_box",visibility="company",icon_name="fiber-box")
    assert marker["point_type"]=="fiber_box"


@pytest.mark.asyncio
async def test_appearance_edit_keeps_fixed_coordinates_and_visibility(db_session, api_client):
    _, _, headers, _, _, line = await route_context(db_session, api_client)
    result = await place(api_client, headers, line)
    marker, changed = result["marker"], result["connection"]
    updated = await api_client.patch(f"/api/v1/map/markers/{marker['id']}", headers=headers, json={
        "latitude": marker["latitude"], "longitude": marker["longitude"],
        "name": "Новое название колодца", "icon_color": "#112233", "expected_version": marker["version"],
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["route_attachment"]["connection_id"] == line["id"]
    denied = await api_client.patch(f"/api/v1/map/connections/{line['id']}", headers=headers,
        json=update_payload(changed, visibility="private"))
    assert denied.status_code == 409 and denied.json()["detail"]["code"] == "route_objects_visibility"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["route-objects", "installation-boundaries"])
async def test_new_operations_rollback_every_write(db_session, api_client, monkeypatch, operation):
    _, _, headers, _, _, line = await route_context(db_session, api_client, installation_methods=["aerial"] * 3)
    payload = split_payload(line)
    if operation == "route-objects":
        payload["marker"]["point_type"] = "transition"
    else:
        payload.pop("marker")
    payload["installation_after"] = "duct"
    original_flush = AsyncSession.flush

    async def fail_final_flush(session, *args, **kwargs):
        # Place has already inserted the marker and modified the route before
        # its binding flush. Boundary has modified geometry before this flush.
        if any(isinstance(entity, MapRouteObject) for entity in session.new) or (
            operation == "installation-boundaries" and any(isinstance(entity, MapConnection) for entity in session.dirty)
        ):
            raise RuntimeError("injected route write failure")
        return await original_flush(session, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "flush", fail_final_flush)
        with pytest.raises(RuntimeError, match="injected route"):
            await api_client.post(f"/api/v1/map/connections/{line['id']}/{operation}", headers=headers, json=payload)
    assert (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json() == line
    assert await db_session.scalar(select(func.count()).select_from(MapRouteObject)) == 0
    assert await db_session.scalar(select(func.count()).select_from(MapMarker).where(MapMarker.point_type == "transition")) == 0


@pytest.mark.asyncio
async def test_parallel_placement_and_boundary_have_one_winner(db_session, api_client):
    from schemas.map_connections import MapConnectionPlace, MapInstallationBoundary
    from services.map_connections import place_route_object, set_installation_boundary
    company, _, _, _, _, line = await route_context(db_session, api_client, visibility="private")
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False, autoflush=False)
    payload = split_payload(line)
    payload["marker"]["point_type"] = "pole"
    placement = MapConnectionPlace.model_validate(payload)
    payload.pop("marker")
    boundary = MapInstallationBoundary.model_validate({**payload, "installation_after": "duct"})

    async def attempt(function, data):
        async with factory() as session:
            try:
                return await function(session, company_id=company, user_id=line["owner_user_id"], can_manage=True, connection_id=line["id"], data=data)
            except MapOperationError as error:
                return error

    await db_session.commit()
    results = await asyncio.gather(attempt(place_route_object, placement), attempt(set_installation_boundary, boundary))
    failure = [result for result in results if isinstance(result, MapOperationError)]
    assert len(failure) == 1 and failure[0].detail["code"] == "stale_version"
    assert await db_session.scalar(select(func.count()).select_from(MapConnection)) == 1
    assert await db_session.scalar(select(func.count()).select_from(MapRouteObject)) <= 1


@pytest.mark.asyncio
async def test_private_route_anchor_and_boundary_never_leak(db_session, api_client):
    company, token, headers, _, _, line = await route_context(db_session, api_client, visibility="private")
    result = await place(api_client, headers, line)
    marker = result["marker"]
    assert marker["visibility"] == "private" and marker["owner_user_id"] == line["owner_user_id"]
    _, other = await reader(db_session, api_client, company, "private-route-reader")
    payload = split_payload(result["connection"])
    payload["marker"]["point_type"] = "pole"
    for operation in ("route-objects", "installation-boundaries"):
        body = payload if operation == "route-objects" else {key: value for key, value in payload.items() if key != "marker"} | {"installation_after": "duct"}
        url = f"/api/v1/map/connections/{line['id']}/{operation}"
        assert (await api_client.post(url, headers=other, json=body)).status_code == 404
        assert (await api_client.post(url, json=body)).status_code == 401
    assert (await api_client.get(f"/api/v1/map/markers/{marker['id']}", headers=other)).status_code == 404
    from test_map_api import company_headers
    # A valid JWT cannot cross company context even with exact object IDs.
    foreign = company_headers(token, company + 99999)
    assert (await api_client.post(f"/api/v1/map/connections/{line['id']}/route-objects", headers=foreign, json=payload)).status_code in (403, 404)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [["space"] * 3, ["duct"], [1, 1, 1]])
async def test_postgresql_checks_installation_metadata_without_api(db_session, api_client, bad):
    import json
    _, _, _, _, _, line = await route_context(db_session, api_client)
    with pytest.raises(IntegrityError):
        await db_session.execute(text("UPDATE map_connections SET installation_methods=CAST(:value AS jsonb) WHERE id=:id"),
            {"id": line["id"], "value": json.dumps(bad)})
    await db_session.rollback()


@pytest.mark.asyncio
async def test_legacy_corrupt_geometry_can_be_detached_without_losing_marker(db_session, api_client):
    _, _, headers, building, _, line = await route_context(db_session, api_client)
    result = await place(api_client, headers, line)
    # Simulate a legacy import bypassing the protected API. The map must show
    # needs_attention and let the engineer explicitly resolve the attachment.
    await db_session.execute(text("UPDATE buildings SET latitude=NULL,longitude=NULL WHERE id=:id"), {"id": building["id"]})
    await db_session.commit()
    fresh = (await api_client.get(f"/api/v1/map/connections/{line['id']}", headers=headers)).json()
    assert fresh["route_objects"][0]["state"] == "needs_attention"
    response = await api_client.post(f"/api/v1/map/connections/{line['id']}/route-objects/{result['marker']['id']}/detach", headers=headers,
        json={"expected_version": fresh["version"], "expected_geometry_token": fresh["geometry_token"]})
    assert response.status_code == 200, response.text
    assert response.json()["marker"]["latitude"] == result["marker"]["latitude"]
