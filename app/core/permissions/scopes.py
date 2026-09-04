from enum import StrEnum


class PermissionScope(StrEnum):
    SELF = "self"
    OWN_UNIT = "own_unit"
    OWN_UNIT_TREE = "own_unit_tree"
    COMPANY = "company"


SCOPE_RANK: dict[PermissionScope, int] = {
    PermissionScope.SELF: 10,
    PermissionScope.OWN_UNIT: 20,
    PermissionScope.OWN_UNIT_TREE: 30,
    PermissionScope.COMPANY: 40,
}


def get_scope_rank(
    scope: PermissionScope,
) -> int:
    return SCOPE_RANK[scope]


def get_broader_scope(
    first: PermissionScope,
    second: PermissionScope,
) -> PermissionScope:
    if get_scope_rank(first) >= get_scope_rank(second):
        return first

    return second