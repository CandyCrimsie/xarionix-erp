from fastapi import APIRouter

from .v1 import (
    auth,
    redis,
    companies,
    organizational_units,
    company_memberships,
    unit_memberships,
    me,
    permissions,
    roles,
    role_permissions,
    membership_roles
)

router = APIRouter()

router.include_router(auth.router)
router.include_router(redis.router)
router.include_router(companies.router)
router.include_router(organizational_units.router)
router.include_router(company_memberships.router)
router.include_router(unit_memberships.router)
router.include_router(me.router)
router.include_router(permissions.router)
router.include_router(roles.router)
router.include_router(role_permissions.router)
router.include_router(membership_roles.router)