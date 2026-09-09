from enum import StrEnum


class SystemRoleKey(StrEnum):
    ADMINISTRATOR = "administrator"
    COMPANY_MANAGER = "company_manager"
    DEPARTMENT_MANAGER = "department_manager"
    EMPLOYEE = "employee"