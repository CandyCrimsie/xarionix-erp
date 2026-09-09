from core.permissions.codes import (
    PERMISSION_DEFINITIONS,
    PermissionCode,
    get_permission_definition,
)
from core.permissions.scopes import (
    PermissionScope,
)

from core.system_roles import (
    SYSTEM_ROLE_TEMPLATES,
    SystemRoleKey,
    get_system_role_template,
)


def test_every_system_role_has_template():
    template_keys = {
        template.key
        for template
        in SYSTEM_ROLE_TEMPLATES
    }

    assert template_keys == set(
        SystemRoleKey
    )


def test_system_role_template_keys_are_unique():
    keys = [
        template.key
        for template
        in SYSTEM_ROLE_TEMPLATES
    ]

    assert len(keys) == len(
        set(keys)
    )


def test_permission_codes_are_unique_inside_each_template():
    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        permission_codes = [
            item.code
            for item
            in template.permissions
        ]

        assert len(
            permission_codes
        ) == len(
            set(permission_codes)
        )


def test_every_template_permission_uses_allowed_scope():
    for template in (
        SYSTEM_ROLE_TEMPLATES
    ):
        for item in (
            template.permissions
        ):
            definition = (
                get_permission_definition(
                    item.code
                )
            )

            assert definition is not None

            assert (
                item.scope
                in definition.allowed_scopes
            )


def test_administrator_has_every_permission():
    template = (
        get_system_role_template(
            SystemRoleKey.ADMINISTRATOR
        )
    )

    assert template is not None

    expected_codes = {
        definition.code
        for definition
        in PERMISSION_DEFINITIONS
    }

    actual_codes = {
        item.code
        for item
        in template.permissions
    }

    assert actual_codes == expected_codes

    assert all(
        item.scope
        == PermissionScope.COMPANY
        for item
        in template.permissions
    )


def test_non_administrator_templates_cannot_manage_rbac():
    for key in (
        SystemRoleKey.COMPANY_MANAGER,
        SystemRoleKey.DEPARTMENT_MANAGER,
        SystemRoleKey.EMPLOYEE,
    ):
        template = (
            get_system_role_template(
                key
            )
        )

        assert template is not None

        permission_codes = {
            item.code
            for item
            in template.permissions
        }

        assert (
            PermissionCode.ROLES_MANAGE
            not in permission_codes
        )

        assert (
            PermissionCode.COMPANIES_MANAGE
            not in permission_codes
        )


def test_department_manager_is_limited_to_unit_tree_for_management():
    template = (
        get_system_role_template(
            SystemRoleKey.DEPARTMENT_MANAGER
        )
    )

    assert template is not None

    permissions = {
        item.code: item.scope
        for item
        in template.permissions
    }

    assert permissions[
        PermissionCode.MEMBERS_MANAGE
    ] == PermissionScope.OWN_UNIT_TREE

    assert permissions[
        PermissionCode.ROLES_ASSIGN
    ] == PermissionScope.OWN_UNIT_TREE

    assert permissions[
        PermissionCode.ORGANIZATIONAL_UNITS_MANAGE
    ] == PermissionScope.OWN_UNIT_TREE


def test_employee_does_not_receive_management_permissions():
    template = (
        get_system_role_template(
            SystemRoleKey.EMPLOYEE
        )
    )

    assert template is not None

    permission_codes = {
        item.code
        for item
        in template.permissions
    }

    forbidden = {
        PermissionCode.COMPANIES_MANAGE,
        PermissionCode.ORGANIZATIONAL_UNITS_MANAGE,
        PermissionCode.MEMBERS_MANAGE,
        PermissionCode.ROLES_MANAGE,
        PermissionCode.ROLES_ASSIGN,
        PermissionCode.TASKS_DELETE,
        PermissionCode.TASKS_ASSIGN,
    }

    assert (
        permission_codes
        & forbidden
    ) == set()


def test_system_role_template_can_be_resolved_from_string_key():
    template = (
        get_system_role_template(
            "administrator"
        )
    )

    assert template is not None

    assert (
        template.key
        == SystemRoleKey.ADMINISTRATOR
    )


def test_unknown_system_role_template_returns_none():
    assert (
        get_system_role_template(
            "does_not_exist"
        )
        is None
    )