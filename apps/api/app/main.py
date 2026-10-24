from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.profile import router as profile_router
from app.db.bootstrap import bootstrap
from app.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Uvicorn binds the socket only after lifespan startup succeeds, so a
    # raised error here means no HTTP is ever served.
    await bootstrap()
    yield
    await dispose_engine()


app = FastAPI(title="lingua-api", lifespan=lifespan)
app.include_router(profile_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
