from dataclasses import dataclass
from enum import StrEnum

from core.permissions.codes import (
    PERMISSION_DEFINITIONS,
    PermissionCode,
)
from core.permissions.scopes import (
    PermissionScope,
)


class SystemRoleKey(StrEnum):
    ADMINISTRATOR = "administrator"
    COMPANY_MANAGER = "company_manager"
    DEPARTMENT_MANAGER = "department_manager"
    EMPLOYEE = "employee"


@dataclass(
    slots=True,
    frozen=True,
)
class SystemRolePermissionTemplate:
    code: PermissionCode
    scope: PermissionScope


@dataclass(
    slots=True,
    frozen=True,
)
class SystemRoleTemplate:
    key: SystemRoleKey

    name: str
    description: str

    permissions: tuple[
        SystemRolePermissionTemplate,
        ...
    ]

    assignable_role_keys: tuple[
        SystemRoleKey,
        ...
    ]


def _permission(
    code: PermissionCode,
    scope: PermissionScope,
) -> SystemRolePermissionTemplate:
    return SystemRolePermissionTemplate(
        code=code,
        scope=scope,
    )


ADMINISTRATOR_PERMISSIONS = tuple(
    _permission(
        definition.code,
        PermissionScope.COMPANY,
    )
    for definition in PERMISSION_DEFINITIONS
)


COMPANY_MANAGER_PERMISSIONS = (
    _permission(
        PermissionCode.COMPANIES_READ,
        PermissionScope.COMPANY,
    ),

    _permission(
        PermissionCode.ORGANIZATIONAL_UNITS_READ,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.ORGANIZATIONAL_UNITS_MANAGE,
        PermissionScope.COMPANY,
    ),

    _permission(
        PermissionCode.MEMBERS_READ,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.MEMBERS_MANAGE,
        PermissionScope.COMPANY,
    ),

    _permission(
        PermissionCode.ROLES_READ,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.ROLES_ASSIGN,
        PermissionScope.COMPANY,
    ),

    _permission(
        PermissionCode.TASKS_READ,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.TASKS_CREATE,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.TASKS_UPDATE,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.TASKS_DELETE,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.TASKS_ASSIGN,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.TASKS_CLOSE,
        PermissionScope.COMPANY,
    ),
)


DEPARTMENT_MANAGER_PERMISSIONS = (
    _permission(
        PermissionCode.COMPANIES_READ,
        PermissionScope.COMPANY,
    ),

    _permission(
        PermissionCode.ORGANIZATIONAL_UNITS_READ,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.ORGANIZATIONAL_UNITS_MANAGE,
        PermissionScope.OWN_UNIT_TREE,
    ),

    _permission(
        PermissionCode.MEMBERS_READ,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.MEMBERS_MANAGE,
        PermissionScope.OWN_UNIT_TREE,
    ),

    _permission(
        PermissionCode.ROLES_READ,
        PermissionScope.COMPANY,
    ),
    _permission(
        PermissionCode.ROLES_ASSIGN,
        PermissionScope.OWN_UNIT_TREE,
    ),

    _permission(
        PermissionCode.TASKS_READ,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.TASKS_CREATE,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.TASKS_UPDATE,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.TASKS_DELETE,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.TASKS_ASSIGN,
        PermissionScope.OWN_UNIT_TREE,
    ),
    _permission(
        PermissionCode.TASKS_CLOSE,
        PermissionScope.OWN_UNIT_TREE,
    ),
)


EMPLOYEE_PERMISSIONS = (
    _permission(
        PermissionCode.COMPANIES_READ,
        PermissionScope.COMPANY,
    ),

    _permission(
        PermissionCode.ORGANIZATIONAL_UNITS_READ,
        PermissionScope.OWN_UNIT,
    ),

    _permission(
        PermissionCode.MEMBERS_READ,
        PermissionScope.OWN_UNIT,
    ),

    _permission(
        PermissionCode.TASKS_READ,
        PermissionScope.SELF,
    ),
    _permission(
        PermissionCode.TASKS_CREATE,
        PermissionScope.SELF,
    ),
    _permission(
        PermissionCode.TASKS_UPDATE,
        PermissionScope.SELF,
    ),
    _permission(
        PermissionCode.TASKS_CLOSE,
        PermissionScope.SELF,
    ),
)


SYSTEM_ROLE_TEMPLATES = (
    SystemRoleTemplate(
        key=SystemRoleKey.ADMINISTRATOR,
        name="Administrator",
        description=(
            "Full administrative access "
            "within the company."
        ),
        permissions=(
            ADMINISTRATOR_PERMISSIONS
        ),
        assignable_role_keys=(
            SystemRoleKey.ADMINISTRATOR,
            SystemRoleKey.COMPANY_MANAGER,
            SystemRoleKey.DEPARTMENT_MANAGER,
            SystemRoleKey.EMPLOYEE,
        ),
    ),

    SystemRoleTemplate(
        key=SystemRoleKey.COMPANY_MANAGER,
        name="Company Manager",
        description=(
            "Manages company structure, "
            "employees and operational work."
        ),
        permissions=(
            COMPANY_MANAGER_PERMISSIONS
        ),
        assignable_role_keys=(
            SystemRoleKey.DEPARTMENT_MANAGER,
            SystemRoleKey.EMPLOYEE,
        ),
    ),

    SystemRoleTemplate(
        key=SystemRoleKey.DEPARTMENT_MANAGER,
        name="Department Manager",
        description=(
            "Manages employees and work "
            "within the assigned unit tree."
        ),
        permissions=(
            DEPARTMENT_MANAGER_PERMISSIONS
        ),
        assignable_role_keys=(
            SystemRoleKey.EMPLOYEE,
        ),
    ),

    SystemRoleTemplate(
        key=SystemRoleKey.EMPLOYEE,
        name="Employee",
        description=(
            "Basic employee access to own "
            "unit and personal resources."
        ),
        permissions=EMPLOYEE_PERMISSIONS,
        assignable_role_keys=(),
    ),
)


SYSTEM_ROLE_TEMPLATES_BY_KEY = {
    template.key: template
    for template in SYSTEM_ROLE_TEMPLATES
}


def get_system_role_template(
    key: SystemRoleKey | str,
) -> SystemRoleTemplate | None:
    try:
        system_key = SystemRoleKey(
            key
        )
    except ValueError:
        return None

    return SYSTEM_ROLE_TEMPLATES_BY_KEY.get(
        system_key
    )