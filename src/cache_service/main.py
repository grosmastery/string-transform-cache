"""ASGI application entry point (``uvicorn cache_service.main:app``)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cache_service.api import router
from cache_service.config import Settings, get_settings
from cache_service.db import build_engine, init_db
from cache_service.transformer import Transformer, make_transformer


def create_app(settings: Settings | None = None, transformer: Transformer | None = None) -> FastAPI:
    """Build the application; arguments allow tests to inject a database and transformer."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        init_db(engine)
        app.state.engine = engine
        yield
        engine.dispose()

    app = FastAPI(title="Cache service", version="0.1.0", lifespan=lifespan)
    app.state.transformer = transformer or make_transformer(settings.transformer_delay_seconds)
    app.include_router(router)
    return app


app = create_app()
