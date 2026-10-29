from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from api.v1.map import DatabaseSession, MapManageContext, MapReadContext, MapRoute, actor
from schemas.map_workspace import EntityKind, LayerCreate, LayerMove, LayerResponse, LayerUpdate, MapTarget, MemberUpdate, PassportWrite, PreferenceResponse, PreferenceWrite
from services import map_layers, map_passports, map_preferences

router = APIRouter(prefix="/map", tags=["Map workspace"], route_class=MapRoute)
EntityId = Annotated[int, Path(gt=0)]


@router.get("/layers", response_model=list[LayerResponse])
async def layers(context: MapReadContext, session: DatabaseSession):
    return await map_layers.list_layers(session, company_id=context.company.id)


@router.post("/layers", response_model=LayerResponse, status_code=201)
async def create_layer(data: LayerCreate, context: MapManageContext, session: DatabaseSession):
    return await map_layers.save_layer(session, company_id=context.company.id, data=data)


@router.patch("/layers/{layer_id}", response_model=LayerResponse)
async def update_layer(layer_id: int, data: LayerUpdate, context: MapManageContext, session: DatabaseSession):
    return await map_layers.save_layer(session, company_id=context.company.id, data=data, layer_id=layer_id)


@router.delete("/layers/{layer_id}", status_code=204)
async def delete_layer(layer_id: int, expected_version: Annotated[int, Query(gt=0)], context: MapManageContext, session: DatabaseSession):
    await map_layers.delete_layer(session, company_id=context.company.id, layer_id=layer_id, expected_version=expected_version)
    return Response(status_code=204)


@router.put("/layers/{layer_id}/members", response_model=LayerResponse)
async def membership(layer_id: int, data: MemberUpdate, context: MapManageContext, session: DatabaseSession):
    return await map_layers.set_membership(session, company_id=context.company.id, user_id=context.user.id, layer_id=layer_id, data=data)


@router.post("/layers/{layer_id}/move", response_model=list[LayerResponse])
async def move_layer(layer_id: EntityId, data: LayerMove, context: MapManageContext, session: DatabaseSession):
    return await map_layers.move_layer(session, company_id=context.company.id, layer_id=layer_id, data=data)


@router.get("/objects/{kind}/{entity_id}/layers", response_model=list[LayerResponse])
async def memberships(kind: EntityKind, entity_id: EntityId, context: MapReadContext, session: DatabaseSession):
    return await map_layers.target_layers(session, company_id=context.company.id, user_id=context.user.id, target=MapTarget(kind=kind, id=entity_id))


@router.get("/preferences", response_model=PreferenceResponse)
async def preferences(context: MapReadContext, session: DatabaseSession):
    return await map_preferences.get_preferences(session, company_id=context.company.id, user_id=context.user.id)


@router.put("/preferences", response_model=PreferenceResponse)
async def save_preferences(data: PreferenceWrite, context: MapReadContext, session: DatabaseSession):
    return await map_preferences.save_preferences(session, company_id=context.company.id, user_id=context.user.id, data=data)


@router.get("/passports/{kind}/{entity_id}")
async def passport(kind: EntityKind, entity_id: EntityId, context: MapReadContext, session: DatabaseSession):
    return await map_passports.get_passport(session, **await actor(session, context), target=MapTarget(kind=kind, id=entity_id))


@router.put("/passports/{kind}/{entity_id}")
async def save_passport(kind: EntityKind, entity_id: EntityId, data: PassportWrite, context: MapReadContext, session: DatabaseSession):
    return await map_passports.save_passport(session, **await actor(session, context), target=MapTarget(kind=kind, id=entity_id), data=data)


@router.get("/objects/{kind}/{entity_id}/dependencies")
async def dependencies(kind: EntityKind, entity_id: EntityId, context: MapReadContext, session: DatabaseSession):
    from services.address_dependencies import deletion_dependencies
    await map_layers.get_target(session, MapTarget(kind=kind, id=entity_id), company_id=context.company.id, user_id=context.user.id)
    return await deletion_dependencies(session, kind, entity_id, company_id=context.company.id, user_id=context.user.id, allow_empty=True)
