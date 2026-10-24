from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.bootstrap import bootstrap


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Uvicorn binds the socket only after lifespan startup succeeds, so a
    # raised error here means no HTTP is ever served.
    await bootstrap()
    yield


app = FastAPI(title="lingua-api", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
