from dataclasses import dataclass
from enum import StrEnum

from core.permissions.scopes import (
    PermissionScope,
)


class PermissionCode(StrEnum):
    COMPANIES_READ = "companies.read"
    COMPANIES_MANAGE = "companies.manage"

    ORGANIZATIONAL_UNITS_READ = "organizational_units.read"
    ORGANIZATIONAL_UNITS_MANAGE = "organizational_units.manage"

    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"

    ROLES_READ = "roles.read"
    ROLES_MANAGE = "roles.manage"
    ROLES_ASSIGN = "roles.assign"

    TASKS_READ = "tasks.read"
    TASKS_CREATE = "tasks.create"
    TASKS_UPDATE = "tasks.update"
    TASKS_DELETE = "tasks.delete"
    TASKS_ASSIGN = "tasks.assign"
    TASKS_CLOSE = "tasks.close"


COMPANY_ONLY_SCOPES = (
    PermissionScope.COMPANY,
)

UNIT_SCOPES = (
    PermissionScope.OWN_UNIT,
    PermissionScope.OWN_UNIT_TREE,
    PermissionScope.COMPANY,
)

ALL_RESOURCE_SCOPES = (
    PermissionScope.SELF,
    PermissionScope.OWN_UNIT,
    PermissionScope.OWN_UNIT_TREE,
    PermissionScope.COMPANY,
)


@dataclass(slots=True, frozen=True)
class PermissionDefinition:
    code: PermissionCode
    name: str
    module: str

    allowed_scopes: tuple[
        PermissionScope,
        ...
    ]

    description: str | None = None


PERMISSION_DEFINITIONS = (
    PermissionDefinition(
        code=PermissionCode.COMPANIES_READ,
        name="Просмотр компаний",
        module="companies",
        allowed_scopes=COMPANY_ONLY_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.COMPANIES_MANAGE,
        name="Управление компаниями",
        module="companies",
        allowed_scopes=COMPANY_ONLY_SCOPES,
    ),

    PermissionDefinition(
        code=PermissionCode.ORGANIZATIONAL_UNITS_READ,
        name="Просмотр организационной структуры",
        module="organizational_units",
        allowed_scopes=UNIT_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.ORGANIZATIONAL_UNITS_MANAGE,
        name="Управление организационной структурой",
        module="organizational_units",
        allowed_scopes=UNIT_SCOPES,
    ),

    PermissionDefinition(
        code=PermissionCode.MEMBERS_READ,
        name="Просмотр сотрудников компании",
        module="members",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.MEMBERS_MANAGE,
        name="Управление сотрудниками компании",
        module="members",
        allowed_scopes=UNIT_SCOPES,
    ),

    PermissionDefinition(
        code=PermissionCode.ROLES_READ,
        name="Просмотр ролей",
        module="roles",
        allowed_scopes=COMPANY_ONLY_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.ROLES_MANAGE,
        name="Управление ролями",
        module="roles",
        allowed_scopes=COMPANY_ONLY_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.ROLES_ASSIGN,
        name="Назначение ролей сотрудникам",
        module="roles",
        allowed_scopes=UNIT_SCOPES,
    ),

    PermissionDefinition(
        code=PermissionCode.TASKS_READ,
        name="Просмотр задач",
        module="tasks",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_CREATE,
        name="Создание задач",
        module="tasks",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_UPDATE,
        name="Изменение задач",
        module="tasks",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_DELETE,
        name="Удаление задач",
        module="tasks",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_ASSIGN,
        name="Назначение исполнителей задач",
        module="tasks",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_CLOSE,
        name="Закрытие задач",
        module="tasks",
        allowed_scopes=ALL_RESOURCE_SCOPES,
    ),
)


PERMISSION_DEFINITIONS_BY_CODE = {
    definition.code.value: definition
    for definition in PERMISSION_DEFINITIONS
}


def get_permission_definition(
    code: PermissionCode | str,
) -> PermissionDefinition | None:
    permission_code = (
        code.value
        if isinstance(
            code,
            PermissionCode,
        )
        else code
    )

    return PERMISSION_DEFINITIONS_BY_CODE.get(
        permission_code
    )