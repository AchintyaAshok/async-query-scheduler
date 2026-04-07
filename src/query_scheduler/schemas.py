"""Pydantic request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from query_scheduler.models import QueryStatus


class QueryCreate(BaseModel):
    """Request body for submitting a new query."""

    sql: str = Field(..., min_length=1, max_length=10_000)


class QueryResponse(BaseModel):
    """Standard query response (no result rows)."""

    id: uuid.UUID
    status: QueryStatus
    sql: str
    created_at: datetime
    updated_at: datetime
    snowflake_query_id: str | None = None
    error_message: str | None = None
    row_count: int | None = None


class QueryResultResponse(QueryResponse):
    """Query response including result rows (returned on SUCCESS)."""

    result_rows: list[dict] | None = None
