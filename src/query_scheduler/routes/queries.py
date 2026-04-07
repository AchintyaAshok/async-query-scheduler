"""Query submission and status endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from query_scheduler.core.database import get_session
from query_scheduler.core.warehouse.snowflake import SnowflakeWarehouse
from query_scheduler.models import QueryStatus
from query_scheduler.schemas import (
    QueryCreate,
    QueryResponse,
    QueryResultResponse,
)
from query_scheduler.services.query_service import QueryService

router = APIRouter(prefix="/queries", tags=["queries"])

# Module-level warehouse singleton — created once, reused across requests
_warehouse: SnowflakeWarehouse | None = None


def _get_warehouse() -> SnowflakeWarehouse:
    global _warehouse
    if _warehouse is None:
        _warehouse = SnowflakeWarehouse()
    return _warehouse


def _get_service(
    session: AsyncSession = Depends(get_session),
) -> QueryService:
    return QueryService(session=session, warehouse=_get_warehouse())


@router.post("", response_model=QueryResponse, status_code=201)
async def start_query(
    body: QueryCreate,
    service: QueryService = Depends(_get_service),
) -> QueryResponse:
    """Submit a SQL query for async execution against the warehouse."""
    record = await service.start_query(sql=body.sql)
    return QueryResponse.model_validate(record, from_attributes=True)


@router.get("/{query_id}", response_model=QueryResultResponse)
async def get_query_status(
    query_id: uuid.UUID,
    service: QueryService = Depends(_get_service),
) -> QueryResultResponse:
    """Get query status and results (if complete)."""
    record = await service.get_query_status(query_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Query not found")
    response = QueryResultResponse.model_validate(record, from_attributes=True)
    # Only include result_rows on SUCCESS
    if record.status != QueryStatus.SUCCESS:
        response.result_rows = None
    return response
