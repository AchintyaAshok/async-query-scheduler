"""SQLModel table models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class QueryStatus(enum.StrEnum):
    """Lifecycle status of a scheduled query."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class QueryRecord(SQLModel, table=True):
    """Tracks a SQL query submitted for async execution against a warehouse."""

    __tablename__ = "queries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    sql: str = Field(sa_column=Column(Text, nullable=False))
    status: QueryStatus = Field(default=QueryStatus.PENDING, index=True)
    snowflake_query_id: str | None = Field(default=None, index=True)
    result_rows: dict | list | None = Field(default=None, sa_column=Column(JSONB))
    error_message: str | None = None
    row_count: int | None = None
    submitted_by: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
