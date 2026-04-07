"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from query_scheduler.core.database import get_session

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness probe — always returns OK."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict:
    """Readiness probe — verifies database connectivity."""
    try:
        await session.exec_raw("SELECT 1")  # type: ignore[attr-defined]
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "degraded", "database": str(e)}
