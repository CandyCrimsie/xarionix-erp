import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from core.map_domain import MapOperationError

from core.lifespan import lifespan
from core.config import config
from api.routers import router


app = FastAPI(
    title="Xarionix API",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(router, prefix="/api/v1")


@app.exception_handler(MapOperationError)
async def map_domain_error(_request, exc: MapOperationError):
    # Shared coordinate writes can be invoked through the address API too.
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True
    )
