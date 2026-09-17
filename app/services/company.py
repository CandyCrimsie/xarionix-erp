from sqlalchemy.ext.asyncio import AsyncSession

from models.company import Company
from repositories.company import (
    create_company,
    get_company_by_id,
    get_company_subtree,
    get_companies,
)
from schemas.company import (
    CompanyChildCreate,
    CompanyCreate,
    CompanyTreeNodeResponse,
    CompanyUpdate,
    CompanyRootCreate
)

from services.system_roles import (
    sync_system_roles_for_company,
    sync_system_roles_for_company_in_transaction,
)

from core.system_roles import (
    SystemRoleKey,
)

from repositories.company_memberships import (
    create_company_membership,
)

from repositories.membership_roles import (
    create_membership_roles,
)


class CompanyNotFoundError(Exception):
    pass


class ParentCompanyNotFoundError(Exception):
    pass


class CompanyParentCycleError(Exception):
    pass


class CompanyAdministratorRoleUnavailableError(
    Exception
):
    pass


class CompanyRootMoveForbiddenError(
    Exception
):
    pass


class CompanyInactiveParentError(
    Exception
):
    pass


class CompanyRootDeactivationForbiddenError(
    Exception
):
    pass


class CompanyParentInactiveError(
    Exception
):
    pass


async def _validate_parent_change(
    *,
    session: AsyncSession,
    company_id: int,
    parent_id: int | None,
) -> None:
    if parent_id is None:
        return

    if parent_id == company_id:
        raise CompanyParentCycleError

    parent = await get_company_by_id(
        session,
        parent_id,
    )

    if parent is None:
        raise ParentCompanyNotFoundError

    current = parent

    while current.parent_id is not None:
        if current.parent_id == company_id:
            raise CompanyParentCycleError

        current = await get_company_by_id(
            session,
            current.parent_id,
        )

        if current is None:
            break


async def list_companies(
    session: AsyncSession,
) -> list[Company]:
    return await get_companies(session)


async def get_company(
    session: AsyncSession,
    company_id: int,
) -> Company:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    return company


def _sort_company_tree(
    node: CompanyTreeNodeResponse,
) -> None:
    node.children.sort(
        key=lambda child: (
            child.name.casefold(),
            child.id,
        )
    )


    for child in node.children:
        _sort_company_tree(
            child
        )


async def get_company_tree(
    session: AsyncSession,
    company_id: int,
) -> CompanyTreeNodeResponse:
    companies = (
        await get_company_subtree(
            session,
            company_id,
        )
    )


    if not companies:
        raise CompanyNotFoundError


    nodes = {
        company.id:
            CompanyTreeNodeResponse(
                id=company.id,
                parent_id=company.parent_id,

                name=company.name,
                short_name=company.short_name,

                is_active=company.is_active,

                created_at=company.created_at,
                updated_at=company.updated_at,

                children=[],
            )

        for company
        in companies
    }


    root = nodes.get(
        company_id
    )


    if root is None:
        raise CompanyNotFoundError


    for company in companies:
        if (
            company.id
            == company_id
        ):
            continue


        if company.parent_id is None:
            continue


        parent = nodes.get(
            company.parent_id
        )


        if parent is None:
            continue


        parent.children.append(
            nodes[
                company.id
            ]
        )


    _sort_company_tree(
        root
    )


    return root


async def update_company_metadata_within_tree(
    session: AsyncSession,
    *,
    root_company_id: int,
    company_id: int,
    data: CompanyUpdate,
) -> Company:
    companies = (
        await get_company_subtree(
            session,
            root_company_id,
        )
    )


    if not companies:
        raise CompanyNotFoundError


    company = next(
        (
            candidate
            for candidate in companies
            if candidate.id == company_id
        ),
        None,
    )


    #
    # Target вне текущего subtree
    # считается недоступным.
    #
    if company is None:
        raise CompanyNotFoundError


    #
    # Этот service меняет только metadata.
    # Иерархия и activation имеют
    # отдельные операции.
    #
    update_data = data.model_dump(
        exclude_unset=True,
        include={
            "name",
            "short_name",
        },
    )


    for field, value in update_data.items():
        setattr(
            company,
            field,
            value,
        )


    await session.commit()

    await session.refresh(
        company
    )


    return company


async def move_company_within_tree(
    session: AsyncSession,
    *,
    root_company_id: int,
    company_id: int,
    parent_id: int,
) -> Company:
    companies = (
        await get_company_subtree(
            session,
            root_company_id,
        )
    )


    if not companies:
        raise CompanyNotFoundError


    companies_by_id = {
        company.id: company
        for company
        in companies
    }


    if (
        company_id
        == root_company_id
    ):
        raise (
            CompanyRootMoveForbiddenError
        )


    company = companies_by_id.get(
        company_id
    )

    parent = companies_by_id.get(
        parent_id
    )


        #
    # Не раскрываем существование
    # компаний вне текущего subtree.
    #
    if (
        company is None
        or parent is None
    ):
        raise CompanyNotFoundError


    if (
        company.is_active
        and not parent.is_active
    ):
        raise (
            CompanyInactiveParentError
        )


    if (
        company.parent_id
        == parent_id
    ):
        return company


    await _validate_parent_change(
        session=session,
        company_id=company.id,
        parent_id=parent.id,
    )


    company.parent_id = (
        parent.id
    )


    await session.commit()

    await session.refresh(
        company
    )


    return company


async def set_company_active_state_within_tree(
    session: AsyncSession,
    *,
    root_company_id: int,
    company_id: int,
    is_active: bool,
) -> Company:
    companies = (
        await get_company_subtree(
            session,
            root_company_id,
        )
    )


    if not companies:
        raise CompanyNotFoundError


    companies_by_id = {
        company.id: company
        for company
        in companies
    }


    company = companies_by_id.get(
        company_id
    )


    #
    # Не раскрываем компании
    # вне текущего subtree.
    #
    if company is None:
        raise CompanyNotFoundError


    #
    # Текущий root нельзя выключить
    # через его собственный context.
    #
    if (
        company_id
        == root_company_id
        and not is_active
    ):
        raise (
            CompanyRootDeactivationForbiddenError
        )


    #
    # Root уже активен, иначе сам
    # CurrentCompanyContext не был бы
    # создан.
    #
    if (
        company_id
        == root_company_id
    ):
        return company


    if not is_active:
        subtree = (
            await get_company_subtree(
                session,
                company_id,
            )
        )


        #
        # Деактивация всегда каскадная.
        #
        for subtree_company in subtree:
            subtree_company.is_active = (
                False
            )


        await session.commit()

        await session.refresh(
            company
        )


        return company


    #
    # При reactivation непосредственный
    # parent обязан быть активен.
    #
    if company.parent_id is None:
        raise CompanyNotFoundError


    parent = companies_by_id.get(
        company.parent_id
    )


    if parent is None:
        raise CompanyNotFoundError


    if not parent.is_active:
        raise CompanyParentInactiveError


    if company.is_active:
        return company


    company.is_active = True


    await session.commit()

    await session.refresh(
        company
    )


    return company


async def create_new_company(
    session: AsyncSession,
    data: CompanyCreate,
) -> Company:
    if data.parent_id is not None:
        parent = await get_company_by_id(
            session,
            data.parent_id,
        )

        if parent is None:
            raise ParentCompanyNotFoundError

    company = await create_company(
        session,
        name=data.name,
        short_name=data.short_name,
        parent_id=data.parent_id,
    )

    #
    # create_company() уже сделал flush(),
    # поэтому ID нам доступен до COMMIT.
    #
    company_id = company.id

    #
    # ВАЖНО:
    # commit здесь самостоятельно
    # больше не делаем.
    #
    # System-role service закоммитит
    # Company + roles + permissions +
    # delegations одной транзакцией.
    #
    await sync_system_roles_for_company(
        session,
        company_id=company_id,
    )

    await session.refresh(
        company
    )

    return company


async def _create_company_with_administrator(
    session: AsyncSession,
    *,
    administrator_user_id: int,
    parent_company_id: int | None,
    data: CompanyChildCreate,
) -> Company:
    try:
        company = await create_company(
            session,
            name=data.name,
            short_name=data.short_name,
            parent_id=parent_company_id,
        )


        (
            system_roles,
            _,
        ) = (
            await sync_system_roles_for_company_in_transaction(
                session,
                company_id=company.id,
            )
        )


        administrator_role = next(
            (
                role
                for role in system_roles
                if (
                    role.system_key
                    == (
                        SystemRoleKey
                        .ADMINISTRATOR
                        .value
                    )
                )
            ),
            None,
        )


        if administrator_role is None:
            raise (
                CompanyAdministratorRoleUnavailableError
            )


        membership = (
            await create_company_membership(
                session,
                user_id=(
                    administrator_user_id
                ),
                company_id=company.id,
            )
        )


        await create_membership_roles(
            session,
            company_membership_id=(
                membership.id
            ),
            role_ids=[
                administrator_role.id,
            ],
        )


        await session.commit()

    except Exception:
        await session.rollback()
        raise


    await session.refresh(
        company
    )


    return company


async def create_child_company_with_administrator(
    session: AsyncSession,
    *,
    parent_company_id: int,
    administrator_user_id: int,
    data: CompanyChildCreate,
) -> Company:
    parent = await get_company_by_id(
        session,
        parent_company_id,
    )


    if (
        parent is None
        or not parent.is_active
    ):
        raise ParentCompanyNotFoundError


    return await _create_company_with_administrator(
        session,
        administrator_user_id=(
            administrator_user_id
        ),
        parent_company_id=(
            parent_company_id
        ),
        data=data,
    )


async def create_root_company_with_administrator(
    session: AsyncSession,
    *,
    administrator_user_id: int,
    data: CompanyRootCreate,
) -> Company:
    return await _create_company_with_administrator(
        session,
        administrator_user_id=(
            administrator_user_id
        ),
        parent_company_id=None,
        data=data,
    )


async def update_company(
    session: AsyncSession,
    company_id: int,
    data: CompanyUpdate,
) -> Company:
    company = await get_company_by_id(
        session,
        company_id,
    )

    if company is None:
        raise CompanyNotFoundError

    update_data = data.model_dump(
        exclude_unset=True,
    )

    if "parent_id" in update_data:
        parent_id = update_data["parent_id"]

        await _validate_parent_change(
            session=session,
            company_id=company.id,
            parent_id=parent_id,
        )

    for field, value in update_data.items():
        setattr(
            company,
            field,
            value,
        )

    await session.commit()
    await session.refresh(company)

    return company