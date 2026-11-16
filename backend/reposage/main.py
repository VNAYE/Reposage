"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from reposage.api.routes import build_router
from reposage.config import Settings
from reposage.core.container import Container, build_container


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Build the app. Both arguments can be overridden in tests."""
    settings = settings or Settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await container.startup()
        try:
            yield
        finally:
            await container.shutdown()

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_router(container))
    app.state.container = container

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs", "health": "/api/health"}

    return app
