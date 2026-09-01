from fastapi import APIRouter

from .v1 import auth, redis

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(redis.router, prefix="/redis", tags=["Redis"])