"""Snowflake warehouse implementation using snowflake-connector-python."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from functools import partial

import structlog
from snowflake.connector import DictCursor, SnowflakeConnection, connect
from snowflake.connector.errors import ProgrammingError

from query_scheduler.core.config import settings
from query_scheduler.core.warehouse.base import (
    AbstractWarehouse,
    WarehouseQueryResult,
    WarehouseQueryStatus,
)

logger = structlog.get_logger(__name__)

# Snowflake query status codes → our status enum
_STATUS_MAP: dict[str, WarehouseQueryStatus] = {
    "RUNNING": WarehouseQueryStatus.RUNNING,
    "RESUMING_WAREHOUSE": WarehouseQueryStatus.RUNNING,
    "QUEUED": WarehouseQueryStatus.PENDING,
    "BLOCKED": WarehouseQueryStatus.PENDING,
    "NO_DATA": WarehouseQueryStatus.PENDING,
    "SUCCESS": WarehouseQueryStatus.SUCCESS,
    "ABORTING": WarehouseQueryStatus.FAILED,
    "FAILED_WITH_ERROR": WarehouseQueryStatus.FAILED,
    "FAILED_WITH_INCIDENT": WarehouseQueryStatus.FAILED,
    "DISCONNECTED": WarehouseQueryStatus.FAILED,
}


def _jsonify_value(v: object) -> object:
    """Convert a single value to a JSON-safe type."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.hex()
    return v


def _jsonify_row(row: dict) -> dict:
    """Convert all values in a Snowflake result row to JSON-safe types."""
    return {k: _jsonify_value(v) for k, v in row.items()}


class SnowflakeWarehouse(AbstractWarehouse):
    """Snowflake async query submission and polling via snowflake-connector-python."""

    def __init__(self) -> None:
        self._conn: SnowflakeConnection | None = None

    def _get_connection(self) -> SnowflakeConnection:
        if self._conn is None or self._conn.is_closed():
            self._conn = connect(
                account=settings.snowflake_account,
                user=settings.snowflake_user,
                password=settings.snowflake_password,
                warehouse=settings.snowflake_warehouse,
                database=settings.snowflake_database,
                schema=settings.snowflake_schema,
            )
            logger.info("snowflake_connected", account=settings.snowflake_account)
        return self._conn

    async def submit_query(self, sql: str) -> str:
        """Submit SQL asynchronously. Returns Snowflake query ID."""
        loop = asyncio.get_event_loop()
        conn = self._get_connection()
        cursor = conn.cursor()

        # Execute async — _no_results tells the connector not to wait for results
        await loop.run_in_executor(
            None,
            partial(cursor.execute_async, sql),
        )
        query_id = cursor.sfqid
        logger.info("snowflake_query_submitted", snowflake_query_id=query_id)
        cursor.close()
        return query_id

    async def get_query_status(self, warehouse_query_id: str) -> WarehouseQueryResult:
        """Poll Snowflake for query status and fetch results if complete."""
        loop = asyncio.get_event_loop()
        conn = self._get_connection()

        # Get raw status string from Snowflake
        raw_status = await loop.run_in_executor(
            None,
            partial(conn.get_query_status_throw_if_error, warehouse_query_id),
        )
        status_name = (
            raw_status.name if hasattr(raw_status, "name") else str(raw_status)
        )
        status = _STATUS_MAP.get(status_name, WarehouseQueryStatus.RUNNING)

        logger.info(
            "snowflake_query_polled",
            snowflake_query_id=warehouse_query_id,
            raw_status=status_name,
            mapped_status=status,
        )

        if status == WarehouseQueryStatus.SUCCESS:
            return await self._fetch_results(warehouse_query_id)

        if status == WarehouseQueryStatus.FAILED:
            return WarehouseQueryResult(
                status=status,
                error_message=f"Snowflake query failed with status: {status_name}",
            )

        return WarehouseQueryResult(status=status)

    async def _fetch_results(self, warehouse_query_id: str) -> WarehouseQueryResult:
        """Fetch result rows for a completed query."""
        loop = asyncio.get_event_loop()
        conn = self._get_connection()
        cursor = conn.cursor(DictCursor)

        try:
            await loop.run_in_executor(
                None,
                partial(cursor.get_results_from_sfqid, warehouse_query_id),
            )
            raw_rows = await loop.run_in_executor(None, cursor.fetchall)
            # Convert non-JSON-safe types (datetime, Decimal, etc.)
            rows = [_jsonify_row(r) for r in raw_rows]
            # Cap results to configured max
            capped_rows = rows[: settings.query_result_max_rows]
            logger.info(
                "snowflake_results_fetched",
                snowflake_query_id=warehouse_query_id,
                total_rows=len(rows),
                returned_rows=len(capped_rows),
            )
            return WarehouseQueryResult(
                status=WarehouseQueryStatus.SUCCESS,
                rows=capped_rows,
                row_count=len(rows),
            )
        except ProgrammingError as e:
            logger.error(
                "snowflake_results_fetch_error",
                snowflake_query_id=warehouse_query_id,
                error=str(e),
            )
            return WarehouseQueryResult(
                status=WarehouseQueryStatus.FAILED,
                error_message=str(e),
            )
        finally:
            cursor.close()

    async def close(self) -> None:
        if self._conn and not self._conn.is_closed():
            self._conn.close()
            logger.info("snowflake_disconnected")
