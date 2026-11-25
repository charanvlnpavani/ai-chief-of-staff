"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api import health, v1
from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await get_engine().dispose()


def _operation_id(route: APIRoute) -> str:
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    docs_enabled = not settings.is_production

    app = FastAPI(
        title="Personal OS API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    install_exception_handlers(app)
    app.add_middleware(RequestContextMiddleware, settings=settings)
    app.include_router(health.router)
    app.include_router(v1.router, prefix="/api/v1")
    return app


app = create_app()
