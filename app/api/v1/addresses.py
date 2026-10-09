from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from core.permissions.codes import PermissionCode
from core.permissions.scopes import PermissionScope
from dependencies.authorization import require_permission
from dependencies.company import CurrentCompanyContext
from dependencies.database import get_session
from schemas.addresses import (
    AddressObjectCreate,
    AddressObjectResponse,
    AddressObjectTreeResponse,
    AddressObjectUpdate,
    AddressSearchResponse,
    AddressTypeCreate,
    AddressTypeResponse,
    AddressTypeUpdate,
    BuildingCreate,
    BuildingResponse,
    BuildingUpdate,
    EntranceCreate,
    EntranceResponse,
    EntranceUpdate,
    LocationCreate,
    LocationResponse,
    LocationUpdate,
)
from services.address_hierarchy import (
    AddressHierarchyCycleError,
    AddressParentNotFoundError,
    InvalidAddressHierarchyTransitionError,
)
from services.address_types import (
    AddressTypeDuplicateError,
    AddressTypeInUseError,
    AddressTypeNotFoundError as CatalogAddressTypeNotFoundError,
    SystemAddressTypeProtectedError,
    create_address_type,
    delete_address_type,
    get_address_types,
    update_address_type,
)
from services.addresses import (
    AddressObjectNotEmptyError,
    AddressObjectNotFoundError,
    AddressTypeNotFoundError,
    BuildingNotEmptyError,
    BuildingNotFoundError,
    DuplicateAddressObjectError,
    DuplicateBuildingError,
    DuplicateEntranceError,
    EntranceNotEmptyError,
    EntranceNotFoundError,
    LocationEntranceMismatchError,
    LocationNotEmptyError,
    LocationNotFoundError,
    create_address_object,
    create_building,
    create_entrance,
    create_location,
    delete_address_object,
    delete_building,
    delete_entrance,
    delete_location,
    get_address_object,
    get_address_object_tree,
    get_address_objects,
    get_building_response,
    get_buildings,
    get_entrances,
    get_locations,
    search_addresses,
    update_address_object,
    update_building,
    update_entrance,
    update_location,
)


router = APIRouter(tags=["Addresses"])


AddressReadContext = Annotated[
    CurrentCompanyContext,
    Depends(
        require_permission(
            PermissionCode.ADDRESSES_READ,
            minimum_scope=PermissionScope.COMPANY,
        )
    ),
]
AddressManageContext = Annotated[
    CurrentCompanyContext,
    Depends(
        require_permission(
            PermissionCode.ADDRESSES_MANAGE,
            minimum_scope=PermissionScope.COMPANY,
        )
    ),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


def _raise_address_error(exc: Exception) -> None:
    if isinstance(
        exc,
        (
            AddressObjectNotFoundError,
            AddressParentNotFoundError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address object not found",
        )
    if isinstance(
        exc,
        (AddressTypeNotFoundError, CatalogAddressTypeNotFoundError),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address type not found",
        )
    if isinstance(exc, BuildingNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Building not found",
        )
    if isinstance(exc, EntranceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrance not found",
        )
    if isinstance(exc, LocationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )
    if isinstance(
        exc,
        (
            DuplicateAddressObjectError,
            DuplicateBuildingError,
            DuplicateEntranceError,
            AddressTypeDuplicateError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An identical address record already exists",
        )
    if isinstance(exc, AddressHierarchyCycleError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Address hierarchy cycle detected",
        )
    if isinstance(exc, InvalidAddressHierarchyTransitionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invalid address hierarchy transition",
        )
    if isinstance(exc, LocationEntranceMismatchError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entrance belongs to another building",
        )
    if isinstance(
        exc,
        (
            AddressObjectNotEmptyError,
            BuildingNotEmptyError,
            EntranceNotEmptyError,
            LocationNotEmptyError,
            AddressTypeInUseError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Address record has dependent data",
        )
    if isinstance(exc, SystemAddressTypeProtectedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="System address type is protected",
        )
    raise exc


@router.get("/address-types", response_model=list[AddressTypeResponse])
async def list_address_types_endpoint(
    session: DatabaseSession,
    _context: AddressReadContext,
) -> list[AddressTypeResponse]:
    return await get_address_types(session)


@router.post(
    "/address-types",
    response_model=AddressTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_address_type_endpoint(
    data: AddressTypeCreate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> AddressTypeResponse:
    try:
        return await create_address_type(session, data)
    except AddressTypeDuplicateError as exc:
        _raise_address_error(exc)


@router.patch(
    "/address-types/{address_type_id}",
    response_model=AddressTypeResponse,
)
async def update_address_type_endpoint(
    address_type_id: int,
    data: AddressTypeUpdate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> AddressTypeResponse:
    try:
        return await update_address_type(session, address_type_id, data)
    except (
        CatalogAddressTypeNotFoundError,
        SystemAddressTypeProtectedError,
    ) as exc:
        _raise_address_error(exc)


@router.delete(
    "/address-types/{address_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_address_type_endpoint(
    address_type_id: int,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> Response:
    try:
        await delete_address_type(session, address_type_id)
    except (
        CatalogAddressTypeNotFoundError,
        SystemAddressTypeProtectedError,
        AddressTypeInUseError,
    ) as exc:
        _raise_address_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/address-objects",
    response_model=list[AddressObjectResponse],
)
async def list_address_objects_endpoint(
    session: DatabaseSession,
    _context: AddressReadContext,
    parent_id: Annotated[int | None, Query()] = None,
) -> list[AddressObjectResponse]:
    try:
        return await get_address_objects(session, parent_id=parent_id)
    except AddressObjectNotFoundError as exc:
        _raise_address_error(exc)


@router.get(
    "/address-objects/tree",
    response_model=list[AddressObjectTreeResponse],
)
async def address_object_tree_endpoint(
    session: DatabaseSession,
    _context: AddressReadContext,
) -> list[AddressObjectTreeResponse]:
    return await get_address_object_tree(session)


@router.post(
    "/address-objects",
    response_model=AddressObjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_address_object_endpoint(
    data: AddressObjectCreate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> AddressObjectResponse:
    try:
        return await create_address_object(session, data)
    except (
        AddressTypeNotFoundError,
        AddressParentNotFoundError,
        InvalidAddressHierarchyTransitionError,
        DuplicateAddressObjectError,
    ) as exc:
        _raise_address_error(exc)


@router.get(
    "/address-objects/{address_object_id}",
    response_model=AddressObjectResponse,
)
async def get_address_object_endpoint(
    address_object_id: int,
    session: DatabaseSession,
    _context: AddressReadContext,
) -> AddressObjectResponse:
    try:
        return await get_address_object(session, address_object_id)
    except AddressObjectNotFoundError as exc:
        _raise_address_error(exc)


@router.patch(
    "/address-objects/{address_object_id}",
    response_model=AddressObjectResponse,
)
async def update_address_object_endpoint(
    address_object_id: int,
    data: AddressObjectUpdate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> AddressObjectResponse:
    try:
        return await update_address_object(session, address_object_id, data)
    except (
        AddressObjectNotFoundError,
        AddressTypeNotFoundError,
        AddressParentNotFoundError,
        AddressHierarchyCycleError,
        InvalidAddressHierarchyTransitionError,
        DuplicateAddressObjectError,
    ) as exc:
        _raise_address_error(exc)


@router.delete(
    "/address-objects/{address_object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_address_object_endpoint(
    address_object_id: int,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> Response:
    try:
        await delete_address_object(session, address_object_id)
    except (AddressObjectNotFoundError, AddressObjectNotEmptyError) as exc:
        _raise_address_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/address-objects/{address_object_id}/buildings",
    response_model=list[BuildingResponse],
)
async def list_buildings_endpoint(
    address_object_id: int,
    session: DatabaseSession,
    _context: AddressReadContext,
) -> list[BuildingResponse]:
    try:
        return await get_buildings(session, address_object_id)
    except AddressObjectNotFoundError as exc:
        _raise_address_error(exc)


@router.post(
    "/address-objects/{address_object_id}/buildings",
    response_model=BuildingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_building_endpoint(
    address_object_id: int,
    data: BuildingCreate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> BuildingResponse:
    payload = data.model_copy(update={"address_object_id": address_object_id})
    try:
        return await create_building(session, payload)
    except (
        AddressParentNotFoundError,
        InvalidAddressHierarchyTransitionError,
        DuplicateBuildingError,
    ) as exc:
        _raise_address_error(exc)


@router.get("/buildings/{building_id}", response_model=BuildingResponse)
async def get_building_endpoint(
    building_id: int,
    session: DatabaseSession,
    _context: AddressReadContext,
) -> BuildingResponse:
    try:
        return await get_building_response(session, building_id)
    except BuildingNotFoundError as exc:
        _raise_address_error(exc)


@router.patch("/buildings/{building_id}", response_model=BuildingResponse)
async def update_building_endpoint(
    building_id: int,
    data: BuildingUpdate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> BuildingResponse:
    try:
        return await update_building(session, building_id, data)
    except (
        BuildingNotFoundError,
        AddressParentNotFoundError,
        InvalidAddressHierarchyTransitionError,
        DuplicateBuildingError,
    ) as exc:
        _raise_address_error(exc)


@router.delete(
    "/buildings/{building_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_building_endpoint(
    building_id: int,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> Response:
    try:
        await delete_building(session, building_id)
    except (BuildingNotFoundError, BuildingNotEmptyError) as exc:
        _raise_address_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/buildings/{building_id}/entrances",
    response_model=list[EntranceResponse],
)
async def list_entrances_endpoint(
    building_id: int,
    session: DatabaseSession,
    _context: AddressReadContext,
) -> list[EntranceResponse]:
    try:
        return await get_entrances(session, building_id)
    except BuildingNotFoundError as exc:
        _raise_address_error(exc)


@router.post(
    "/buildings/{building_id}/entrances",
    response_model=EntranceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_entrance_endpoint(
    building_id: int,
    data: EntranceCreate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> EntranceResponse:
    try:
        return await create_entrance(session, building_id, data)
    except (BuildingNotFoundError, DuplicateEntranceError) as exc:
        _raise_address_error(exc)


@router.patch("/entrances/{entrance_id}", response_model=EntranceResponse)
async def update_entrance_endpoint(
    entrance_id: int,
    data: EntranceUpdate,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> EntranceResponse:
    try:
        return await update_entrance(session, entrance_id, data)
    except (EntranceNotFoundError, DuplicateEntranceError) as exc:
        _raise_address_error(exc)


@router.delete(
    "/entrances/{entrance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_entrance_endpoint(
    entrance_id: int,
    session: DatabaseSession,
    _context: AddressManageContext,
) -> Response:
    try:
        await delete_entrance(session, entrance_id)
    except (EntranceNotFoundError, EntranceNotEmptyError) as exc:
        _raise_address_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/buildings/{building_id}/locations",
    response_model=list[LocationResponse],
)
async def list_locations_endpoint(
    building_id: int,
    session: DatabaseSession,
    context: AddressReadContext,
) -> list[LocationResponse]:
    try:
        return await get_locations(
            session,
            company_id=context.company.id,
            building_id=building_id,
        )
    except BuildingNotFoundError as exc:
        _raise_address_error(exc)


@router.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location_endpoint(
    data: LocationCreate,
    session: DatabaseSession,
    context: AddressManageContext,
) -> LocationResponse:
    try:
        return await create_location(
            session,
            company_id=context.company.id,
            data=data,
        )
    except (
        BuildingNotFoundError,
        EntranceNotFoundError,
        LocationEntranceMismatchError,
    ) as exc:
        _raise_address_error(exc)


@router.patch("/locations/{location_id}", response_model=LocationResponse)
async def update_location_endpoint(
    location_id: int,
    data: LocationUpdate,
    session: DatabaseSession,
    context: AddressManageContext,
) -> LocationResponse:
    try:
        return await update_location(
            session,
            company_id=context.company.id,
            location_id=location_id,
            data=data,
        )
    except (
        LocationNotFoundError,
        BuildingNotFoundError,
        EntranceNotFoundError,
        LocationEntranceMismatchError,
    ) as exc:
        _raise_address_error(exc)


@router.delete(
    "/locations/{location_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_location_endpoint(
    location_id: int,
    session: DatabaseSession,
    context: AddressManageContext,
) -> Response:
    try:
        await delete_location(
            session,
            company_id=context.company.id,
            location_id=location_id,
        )
    except (LocationNotFoundError, LocationNotEmptyError) as exc:
        _raise_address_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/addresses/search", response_model=AddressSearchResponse)
async def search_addresses_endpoint(
    session: DatabaseSession,
    _context: AddressReadContext,
    q: Annotated[str, Query(min_length=1, max_length=255)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AddressSearchResponse:
    return await search_addresses(
        session,
        query=q,
        limit=limit,
        offset=offset,
    )
