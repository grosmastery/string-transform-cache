"""ASGI application entry point (``uvicorn cache_service.main:app``)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cache_service.api import router
from cache_service.db import get_engine, init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db(get_engine())
    yield


app = FastAPI(title="Cache service", version="0.1.0", lifespan=lifespan)
app.include_router(router)
