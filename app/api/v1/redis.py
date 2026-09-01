from fastapi import APIRouter

from database.redis import redis_client


router = APIRouter(
    prefix="/redis",
    tags=["Redis"],
)


@router.get("/ping")
async def redis_ping():
    result = await redis_client.ping()

    return {
        "redis": result,
    }