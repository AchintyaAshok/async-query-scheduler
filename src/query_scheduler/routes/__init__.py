"""Route aggregation."""

from fastapi import APIRouter

from query_scheduler.routes.health import router as health_router
from query_scheduler.routes.queries import router as queries_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(queries_router)
