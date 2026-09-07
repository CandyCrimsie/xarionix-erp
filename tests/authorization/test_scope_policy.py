from core.permissions.codes import (
    PermissionCode,
    get_permission_definition,
)
from core.permissions.scopes import (
    PermissionScope,
)


def get_scopes(
    permission: PermissionCode,
) -> set[PermissionScope]:
    definition = get_permission_definition(
        permission
    )

    assert definition is not None

    return set(
        definition.allowed_scopes
    )


def test_companies_read_is_company_only():
    assert get_scopes(
        PermissionCode.COMPANIES_READ
    ) == {
        PermissionScope.COMPANY,
    }


def test_companies_manage_is_company_only():
    assert get_scopes(
        PermissionCode.COMPANIES_MANAGE
    ) == {
        PermissionScope.COMPANY,
    }


def test_members_read_allows_self():
    scopes = get_scopes(
        PermissionCode.MEMBERS_READ
    )

    assert PermissionScope.SELF in scopes


def test_members_manage_does_not_allow_self():
    scopes = get_scopes(
        PermissionCode.MEMBERS_MANAGE
    )

    assert (
        PermissionScope.SELF
        not in scopes
    )


def test_members_manage_allows_unit_scopes():
    assert get_scopes(
        PermissionCode.MEMBERS_MANAGE
    ) == {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
        PermissionScope.COMPANY,
    }


def test_roles_manage_is_company_only():
    assert get_scopes(
        PermissionCode.ROLES_MANAGE
    ) == {
        PermissionScope.COMPANY,
    }


def test_roles_assign_supports_delegation():
    assert get_scopes(
        PermissionCode.ROLES_ASSIGN
    ) == {
        PermissionScope.OWN_UNIT,
        PermissionScope.OWN_UNIT_TREE,
        PermissionScope.COMPANY,
    }