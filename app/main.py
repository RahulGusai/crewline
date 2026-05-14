"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import register_error_handlers
from app.auth.middleware import AuthMiddleware
from app.config import get_settings
from app.logging_config import configure_logging
from app.routes import api_router

settings = get_settings()
configure_logging(settings)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("crewline.startup", environment=settings.environment)
    yield
    logger.info("crewline.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Crewline",
        description="Backend for the autonomous engineering agent platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(AuthMiddleware)

    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-CSRF-Token"],
        )

    register_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
