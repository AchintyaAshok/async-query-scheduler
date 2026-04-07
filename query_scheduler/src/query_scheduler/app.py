"""FastAPI application factory with lifespan management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from query_scheduler.core.config import settings
from query_scheduler.core.database import close_db, init_db
from query_scheduler.core.logging import get_logger, setup_logging
from query_scheduler.core.telemetry import setup_telemetry, shutdown_telemetry
from query_scheduler.middleware.access_control import AccessControlMiddleware
from query_scheduler.middleware.query_sanitization import (
    QuerySanitizationMiddleware,
)
from query_scheduler.routes import api_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    setup_telemetry()
    logger.info("starting", app_name=settings.app_name, env=settings.app_env)

    await init_db()
    logger.info("database_initialized")

    # Instrument FastAPI with OpenTelemetry if enabled
    if settings.otel_enabled:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
            logger.info("otel_instrumented")
        except ImportError:
            logger.warning("otel_enabled_but_not_installed")

    yield

    logger.info("shutting_down")
    await close_db()
    shutdown_telemetry()


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
)

# Middleware — outermost runs first (access control before sanitization)
app.add_middleware(QuerySanitizationMiddleware)
app.add_middleware(AccessControlMiddleware)

app.include_router(api_router)
