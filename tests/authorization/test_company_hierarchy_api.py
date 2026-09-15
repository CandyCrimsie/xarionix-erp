import pytest

from httpx import AsyncClient

from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from core.system_roles import (
    SystemRoleKey,
)

from repositories.company_memberships import (
    get_company_membership_by_user,
)

from repositories.membership_roles import (
    get_membership_roles,
)


async def initialize_and_login(
    api_client: AsyncClient,
) -> tuple[
    dict,
    dict,
]:
    setup_response = (
        await api_client.post(
            "/api/v1/setup/initialize",
            json={
                "company": {
                    "name": "Main Company",
                    "short_name": "MAIN",
                },
                "administrator": {
                    "username": "admin",
                    "password": "password123",
                },
            },
        )
    )

    assert (
        setup_response.status_code
        == 201
    )


    login_response = (
        await api_client.post(
            "/api/v1/auth/login",
            json={
                "username": "admin",
                "password": "password123",
            },
        )
    )

    assert (
        login_response.status_code
        == 200
    )


    return (
        setup_response.json(),
        login_response.json(),
    )


@pytest.mark.asyncio
async def test_administrator_can_create_child_company_and_access_it(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    parent_company_id = (
        setup["company_id"]
    )


    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{parent_company_id}/children"
        ),
        json={
            "name": "Child Company",
            "short_name": "CHILD",
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
            "X-Company-Id": str(
                parent_company_id
            ),
        },
    )


    assert response.status_code == 201

    child = response.json()


    assert (
        child["parent_id"]
        == parent_company_id
    )

    assert (
        child["name"]
        == "Child Company"
    )

    assert (
        child["short_name"]
        == "CHILD"
    )

    assert child["is_active"] is True


    membership = (
        await get_company_membership_by_user(
            db_session,
            company_id=child["id"],
            user_id=setup["user_id"],
        )
    )

    assert membership is not None
    assert membership.is_active is True


    roles = await get_membership_roles(
        db_session,
        membership.id,
    )


    assert len(roles) == 1

    assert (
        roles[0].system_key
        == (
            SystemRoleKey
            .ADMINISTRATOR
            .value
        )
    )


    companies_response = (
        await api_client.get(
            "/api/v1/me/companies",
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
            },
        )
    )


    assert (
        companies_response.status_code
        == 200
    )


    assert {
        company["id"]
        for company
        in companies_response.json()
    } == {
        parent_company_id,
        child["id"],
    }


@pytest.mark.asyncio
async def test_child_creation_requires_path_company_to_match_context(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    parent_company_id = (
        setup["company_id"]
    )


    child_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{parent_company_id}/children"
            ),
            json={
                "name": "Child Company",
            },
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
                "X-Company-Id": str(
                    parent_company_id
                ),
            },
        )
    )

    assert (
        child_response.status_code
        == 201
    )

    child_id = (
        child_response.json()["id"]
    )


    response = await api_client.post(
        (
            f"/api/v1/companies/"
            f"{child_id}/children"
        ),
        json={
            "name": "Forbidden Grandchild",
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
                        # Намеренно оставляем
            # parent company context.
            "X-Company-Id": str(
                parent_company_id
            ),
        },
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_company_tree_returns_nested_descendants(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = (
        setup["company_id"]
    )

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    child_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{root_id}/children"
            ),
            json={
                "name": "Regional Company",
                "short_name": "REG",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert (
        child_response.status_code
        == 201
    )

    child_id = (
        child_response.json()["id"]
    )


    grandchild_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{child_id}/children"
            ),
            json={
                "name": "Local Branch",
                "short_name": "LOCAL",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(child_id),
            },
        )
    )

    assert (
        grandchild_response.status_code
        == 201
    )

    grandchild_id = (
        grandchild_response
        .json()["id"]
    )


    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{root_id}/tree"
        ),
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 200

    tree = response.json()


    assert tree["id"] == root_id
    assert tree["parent_id"] is None

    assert len(
        tree["children"]
    ) == 1


    child = tree["children"][0]

    assert child["id"] == child_id

    assert (
        child["parent_id"]
        == root_id
    )

    assert (
        child["name"]
        == "Regional Company"
    )


    assert len(
        child["children"]
    ) == 1


    grandchild = (
        child["children"][0]
    )

    assert (
        grandchild["id"]
        == grandchild_id
    )

    assert (
        grandchild["parent_id"]
        == child_id
    )

    assert (
        grandchild["name"]
        == "Local Branch"
    )

    assert (
        grandchild["children"]
        == []
    )


@pytest.mark.asyncio
async def test_company_tree_is_scoped_to_requested_root(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = (
        setup["company_id"]
    )

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    first_child_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{root_id}/children"
            ),
            json={
                "name": "First Child",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert (
        first_child_response
        .status_code
        == 201
    )

    first_child_id = (
        first_child_response
        .json()["id"]
    )


    second_child_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{root_id}/children"
            ),
            json={
                "name": "Second Child",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert (
        second_child_response
        .status_code
        == 201
    )

    second_child_id = (
        second_child_response
        .json()["id"]
    )


    grandchild_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{first_child_id}/children"
            ),
            json={
                "name": "Grandchild",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(
                        first_child_id
                    ),
            },
        )
    )

    assert (
        grandchild_response
        .status_code
        == 201
    )

    grandchild_id = (
        grandchild_response
        .json()["id"]
    )


    response = await api_client.get(
        (
            f"/api/v1/companies/"
            f"{first_child_id}/tree"
        ),
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(
                    first_child_id
                ),
        },
    )


    assert response.status_code == 200

    tree = response.json()


    assert (
        tree["id"]
        == first_child_id
    )

    assert {
        child["id"]
        for child
        in tree["children"]
    } == {
        grandchild_id,
    }


    returned_ids = {
        tree["id"],
        *[
            child["id"]
            for child
            in tree["children"]
        ],
    }


    assert root_id not in returned_ids

    assert (
        second_child_id
        not in returned_ids
    )