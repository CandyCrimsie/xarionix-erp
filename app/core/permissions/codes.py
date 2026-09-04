from dataclasses import dataclass
from enum import StrEnum


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


@dataclass(slots=True, frozen=True)
class PermissionDefinition:
    code: PermissionCode
    name: str
    module: str
    description: str | None = None


PERMISSION_DEFINITIONS = (
    PermissionDefinition(
        code=PermissionCode.COMPANIES_READ,
        name="Просмотр компаний",
        module="companies",
    ),
    PermissionDefinition(
        code=PermissionCode.COMPANIES_MANAGE,
        name="Управление компаниями",
        module="companies",
    ),

    PermissionDefinition(
        code=PermissionCode.ORGANIZATIONAL_UNITS_READ,
        name="Просмотр организационной структуры",
        module="organizational_units",
    ),
    PermissionDefinition(
        code=PermissionCode.ORGANIZATIONAL_UNITS_MANAGE,
        name="Управление организационной структурой",
        module="organizational_units",
    ),

    PermissionDefinition(
        code=PermissionCode.MEMBERS_READ,
        name="Просмотр сотрудников компании",
        module="members",
    ),
    PermissionDefinition(
        code=PermissionCode.MEMBERS_MANAGE,
        name="Управление сотрудниками компании",
        module="members",
    ),

    PermissionDefinition(
        code=PermissionCode.ROLES_READ,
        name="Просмотр ролей",
        module="roles",
    ),
    PermissionDefinition(
        code=PermissionCode.ROLES_MANAGE,
        name="Управление ролями",
        module="roles",
    ),
    PermissionDefinition(
        code=PermissionCode.ROLES_ASSIGN,
        name="Назначение ролей сотрудникам",
        module="roles",
    ),

    PermissionDefinition(
        code=PermissionCode.TASKS_READ,
        name="Просмотр задач",
        module="tasks",
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_CREATE,
        name="Создание задач",
        module="tasks",
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_UPDATE,
        name="Изменение задач",
        module="tasks",
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_DELETE,
        name="Удаление задач",
        module="tasks",
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_ASSIGN,
        name="Назначение исполнителей задач",
        module="tasks",
    ),
    PermissionDefinition(
        code=PermissionCode.TASKS_CLOSE,
        name="Закрытие задач",
        module="tasks",
    ),
)