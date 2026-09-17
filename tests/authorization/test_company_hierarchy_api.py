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

from repositories.users import (
    get_user_by_id,
)

from schemas.company import (
    CompanyCreate,
)

from services.company import (
    create_new_company,
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


@pytest.mark.asyncio
async def test_administrator_can_update_company_metadata(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    company_id = (
        setup["company_id"]
    )

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{company_id}"
        ),
        json={
            "name": (
                "  Renamed Company  "
            ),
            "short_name": (
                "  RENAMED  "
            ),
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(company_id),
        },
    )


    assert response.status_code == 200

    company = response.json()


    assert (
        company["id"]
        == company_id
    )

    assert (
        company["name"]
        == "Renamed Company"
    )

    assert (
        company["short_name"]
        == "RENAMED"
    )


@pytest.mark.asyncio
async def test_administrator_can_clear_company_short_name(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    company_id = (
        setup["company_id"]
    )

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{company_id}"
        ),
        json={
            "short_name": None,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(company_id),
        },
    )


    assert response.status_code == 200

    assert (
        response.json()[
            "short_name"
        ]
        is None
    )


@pytest.mark.asyncio
async def test_company_name_cannot_be_null(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    company_id = (
        setup["company_id"]
    )

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{company_id}"
        ),
        json={
            "name": None,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(company_id),
        },
    )


    assert response.status_code == 422


    current_response = (
        await api_client.get(
            (
                f"/api/v1/companies/"
                f"{company_id}"
            ),
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(company_id),
            },
        )
    )


    assert (
        current_response.status_code
        == 200
    )

    assert (
        current_response.json()[
            "name"
        ]
        == "Main Company"
    )


@pytest.mark.asyncio
async def test_company_metadata_update_cannot_change_hierarchy_fields(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    company_id = (
        setup["company_id"]
    )

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    deactivate_response = (
        await api_client.patch(
            (
                f"/api/v1/companies/"
                f"{company_id}"
            ),
            json={
                "is_active": False,
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(company_id),
            },
        )
    )


    assert (
        deactivate_response.status_code
        == 400
    )

    assert (
        deactivate_response.json()
        == {
            "detail": (
                "parent_id and is_active cannot "
                "be changed through this endpoint"
            ),
        }
    )


    move_response = (
        await api_client.patch(
            (
                f"/api/v1/companies/"
                f"{company_id}"
            ),
            json={
                "parent_id": company_id,
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(company_id),
            },
        )
    )


    assert (
        move_response.status_code
        == 400
    )


@pytest.mark.asyncio
async def test_company_metadata_update_requires_matching_company_context(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    parent_id = (
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
                f"{parent_id}/children"
            ),
            json={
                "name": "Child Company",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(parent_id),
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


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{child_id}"
        ),
        json={
            "name": "Hacked Name",
        },
        headers={
            "Authorization":
                authorization,

            # Намеренно остаёмся
            # в parent context.
            "X-Company-Id":
                str(parent_id),
        },
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


    child_get_response = (
        await api_client.get(
            (
                f"/api/v1/companies/"
                f"{child_id}"
            ),
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(child_id),
            },
        )
    )


    assert (
        child_get_response.status_code
        == 200
    )

    assert (
        child_get_response.json()[
            "name"
        ]
        == "Child Company"
    )


@pytest.mark.asyncio
async def test_administrator_can_move_company_inside_current_tree(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    first_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{root_id}/children"
            ),
            json={
                "name": "Branch A",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    second_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{root_id}/children"
            ),
            json={
                "name": "Branch B",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )


    assert first_response.status_code == 201
    assert second_response.status_code == 201


    first_id = (
        first_response.json()["id"]
    )

    second_id = (
        second_response.json()["id"]
    )


    office_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{first_id}/children"
            ),
            json={
                "name": "Office A1",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(first_id),
            },
        )
    )


    assert (
        office_response.status_code
        == 201
    )

    office_id = (
        office_response.json()["id"]
    )


    move_response = (
        await api_client.patch(
            (
                f"/api/v1/companies/"
                f"{root_id}"
                f"/tree/{office_id}"
                "/parent"
            ),
            json={
                "parent_id":
                    second_id,
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
        move_response.status_code
        == 200
    )

    assert (
        move_response.json()[
            "parent_id"
        ]
        == second_id
    )


    tree_response = (
        await api_client.get(
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
    )


    assert tree_response.status_code == 200

    tree = tree_response.json()


    branch_a = next(
        child
        for child
        in tree["children"]
        if child["id"] == first_id
    )

    branch_b = next(
        child
        for child
        in tree["children"]
        if child["id"] == second_id
    )


    assert (
        branch_a["children"]
        == []
    )

    assert {
        child["id"]
        for child
        in branch_b["children"]
    } == {
        office_id,
    }


@pytest.mark.asyncio
async def test_root_company_cannot_be_moved(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

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
                "name": "Child",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert child_response.status_code == 201

    child_id = (
        child_response.json()["id"]
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{root_id}"
            "/parent"
        ),
        json={
            "parent_id":
                child_id,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "Root company cannot be moved"
        ),
    }


@pytest.mark.asyncio
async def test_company_cannot_be_moved_under_its_descendant(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    parent_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{root_id}/children"
            ),
            json={
                "name": "Parent",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert parent_response.status_code == 201

    parent_id = (
        parent_response.json()["id"]
    )


    child_response = (
        await api_client.post(
            (
                f"/api/v1/companies/"
                f"{parent_id}/children"
            ),
            json={
                "name": "Child",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(parent_id),
            },
        )
    )

    assert child_response.status_code == 201

    child_id = (
        child_response.json()["id"]
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{parent_id}"
            "/parent"
        ),
        json={
            "parent_id":
                child_id,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "Company hierarchy cycle detected"
        ),
    }


@pytest.mark.asyncio
async def test_company_move_cannot_target_company_outside_current_tree(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

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
                "name": "Managed Child",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert child_response.status_code == 201

    child_id = (
        child_response.json()["id"]
    )


    outside = await create_new_company(
        db_session,
        CompanyCreate(
            name="Outside Root",
        ),
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{child_id}"
            "/parent"
        ),
        json={
            "parent_id":
                outside.id,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_company_deactivation_cascades_to_descendants(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

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
                "name": "Branch",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert child_response.status_code == 201

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
                "name": "Office",
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


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{child_id}"
            "/activation"
        ),
        json={
            "is_active": False,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 200

    assert (
        response.json()["is_active"]
        is False
    )


    tree_response = await api_client.get(
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


    tree = tree_response.json()

    branch = next(
        item
        for item
        in tree["children"]
        if item["id"] == child_id
    )

    office = branch["children"][0]


    assert branch["is_active"] is False

    assert office["id"] == grandchild_id
    assert office["is_active"] is False

    companies_response = (
        await api_client.get(
            "/api/v1/me/companies",
            headers={
                "Authorization":
                    authorization,
            },
        )
    )


    assert (
        companies_response.status_code
        == 200
    )


    company_ids = {
        company["id"]
        for company
        in companies_response.json()
    }


    assert root_id in company_ids

    assert (
        child_id
        not in company_ids
    )

    assert (
        grandchild_id
        not in company_ids
    )


@pytest.mark.asyncio
async def test_company_reactivation_requires_active_parent(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

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
                "name": "Branch",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
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
                "name": "Office",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(child_id),
            },
        )
    )

    grandchild_id = (
        grandchild_response
        .json()["id"]
    )


    deactivate_response = (
        await api_client.patch(
            (
                f"/api/v1/companies/"
                f"{root_id}"
                f"/tree/{child_id}"
                "/activation"
            ),
            json={
                "is_active": False,
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
        deactivate_response.status_code
        == 200
    )


    #
    # Parent Branch пока inactive.
    #
    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{grandchild_id}"
            "/activation"
        ),
        json={
            "is_active": True,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 409

    assert response.json() == {
        "detail": (
            "Parent company must be active "
            "before company activation"
        ),
    }


    #
    # Сначала восстанавливаем Branch.
    #
    branch_response = (
        await api_client.patch(
            (
                f"/api/v1/companies/"
                f"{root_id}"
                f"/tree/{child_id}"
                "/activation"
            ),
            json={
                "is_active": True,
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )


    assert branch_response.status_code == 200
    assert branch_response.json()["is_active"] is True


    #
    # Office сам при этом всё ещё inactive.
    #
    tree_response = await api_client.get(
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

    tree = tree_response.json()

    branch = next(
        item
        for item
        in tree["children"]
        if item["id"] == child_id
    )

    assert (
        branch["children"][0][
            "is_active"
        ]
        is False
    )


    #
    # Теперь можно восстановить Office.
    #
    office_response = (
        await api_client.patch(
            (
                f"/api/v1/companies/"
                f"{root_id}"
                f"/tree/{grandchild_id}"
                "/activation"
            ),
            json={
                "is_active": True,
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )


    assert office_response.status_code == 200
    assert office_response.json()["is_active"] is True


@pytest.mark.asyncio
async def test_root_company_cannot_be_deactivated(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{root_id}"
            "/activation"
        ),
        json={
            "is_active": False,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "Root company cannot be deactivated"
        ),
    }


@pytest.mark.asyncio
async def test_company_activation_cannot_target_outside_current_tree(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    outside = await create_new_company(
        db_session,
        CompanyCreate(
            name="Outside Company",
        ),
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{outside.id}"
            "/activation"
        ),
        json={
            "is_active": False,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


@pytest.mark.asyncio
async def test_administrator_can_update_descendant_metadata_from_root_context(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

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
                "name": "Old Branch",
                "short_name": "OLD",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert child_response.status_code == 201

    child_id = (
        child_response.json()["id"]
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{child_id}"
            "/metadata"
        ),
        json={
            "name":
                "  New Branch  ",

            "short_name":
                "  NEW  ",
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 200

    company = response.json()


    assert company["id"] == child_id

    assert (
        company["name"]
        == "New Branch"
    )

    assert (
        company["short_name"]
        == "NEW"
    )

    assert (
        company["parent_id"]
        == root_id
    )


@pytest.mark.asyncio
async def test_company_metadata_cannot_target_outside_current_tree(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

    authorization = (
        f"Bearer "
        f"{login['access_token']}"
    )


    outside = await create_new_company(
        db_session,
        CompanyCreate(
            name="Outside Company",
        ),
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{outside.id}"
            "/metadata"
        ),
        json={
            "name":
                "Unauthorized Rename",
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 404

    assert response.json() == {
        "detail": "Company not found",
    }


    await db_session.refresh(
        outside
    )


    assert (
        outside.name
        == "Outside Company"
    )


@pytest.mark.asyncio
async def test_scoped_metadata_endpoint_rejects_hierarchy_fields(
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )

    root_id = setup["company_id"]

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
                "name": "Child",
            },
            headers={
                "Authorization":
                    authorization,

                "X-Company-Id":
                    str(root_id),
            },
        )
    )

    assert child_response.status_code == 201

    child_id = (
        child_response.json()["id"]
    )


    response = await api_client.patch(
        (
            f"/api/v1/companies/"
            f"{root_id}"
            f"/tree/{child_id}"
            "/metadata"
        ),
        json={
            "is_active": False,
        },
        headers={
            "Authorization":
                authorization,

            "X-Company-Id":
                str(root_id),
        },
    )


    assert response.status_code == 400

    assert response.json() == {
        "detail": (
            "parent_id and is_active cannot "
            "be changed through metadata endpoint"
        ),
    }


@pytest.mark.asyncio
async def test_system_administrator_can_create_independent_root_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )


    first_company_id = (
        setup["company_id"]
    )


    response = await api_client.post(
        "/api/v1/companies",
        json={
            "name":
                'АО "ВАСЬКА"',

            "short_name":
                "ВАСЬКА",
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )


    assert response.status_code == 201


    company = response.json()


    assert (
        company["parent_id"]
        is None
    )

    assert (
        company["name"]
        == 'АО "ВАСЬКА"'
    )

    assert (
        company["short_name"]
        == "ВАСЬКА"
    )

    assert (
        company["is_active"]
        is True
    )

    assert (
        company["id"]
        != first_company_id
    )


    membership = (
        await get_company_membership_by_user(
            db_session,
            company_id=(
                company["id"]
            ),
            user_id=(
                setup["user_id"]
            ),
        )
    )


    assert membership is not None

    assert (
        membership.is_active
        is True
    )


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


    company_ids = {
        item["id"]
        for item
        in companies_response.json()
    }


    assert company_ids == {
        first_company_id,
        company["id"],
    }

    first_tree_response = (
        await api_client.get(
            (
                f"/api/v1/companies/"
                f"{first_company_id}/tree"
            ),
            headers={
                "Authorization": (
                    f"Bearer "
                    f"{login['access_token']}"
                ),
                "X-Company-Id": (
                    str(first_company_id)
                ),
            },
        )
    )


    assert (
        first_tree_response.status_code
        == 200
    )


    assert (
        first_tree_response
        .json()["children"]
        == []
    )


@pytest.mark.asyncio
async def test_regular_user_cannot_create_independent_root_company(
    db_session: AsyncSession,
    api_client: AsyncClient,
    clean_test_redis,
):
    setup, login = (
        await initialize_and_login(
            api_client
        )
    )


    user = await get_user_by_id(
        db_session,
        setup["user_id"],
    )


    assert user is not None


    user.is_system_admin = False

    await db_session.commit()


    response = await api_client.post(
        "/api/v1/companies",
        json={
            "name":
                "Unauthorized Company",
        },
        headers={
            "Authorization": (
                f"Bearer "
                f"{login['access_token']}"
            ),
        },
    )


    assert response.status_code == 403

    assert response.json() == {
        "detail": (
            "System administrator "
            "access required"
        ),
    }