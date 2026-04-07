"""Orchestration layer for query submission, status polling, and recovery."""

import uuid
from datetime import datetime

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from query_scheduler.core.warehouse.base import (
    AbstractWarehouse,
    WarehouseQueryStatus,
)
from query_scheduler.models import QueryRecord, QueryStatus

logger = structlog.get_logger(__name__)


class QueryService:
    """Coordinates query lifecycle between Postgres and the warehouse."""

    def __init__(self, session: AsyncSession, warehouse: AbstractWarehouse) -> None:
        self._session = session
        self._warehouse = warehouse

    async def start_query(
        self, sql: str, submitted_by: str | None = None
    ) -> QueryRecord:
        """Persist a new query record, submit to warehouse, return the record."""
        record = QueryRecord(
            id=uuid.uuid4(),
            sql=sql,
            status=QueryStatus.PENDING,
            submitted_by=submitted_by,
        )
        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)

        logger.info("query_persisted", query_id=str(record.id), status=record.status)

        try:
            sfqid = await self._warehouse.submit_query(sql)
            record.snowflake_query_id = sfqid
            record.status = QueryStatus.RUNNING
            record.started_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            self._session.add(record)
            await self._session.commit()
            await self._session.refresh(record)
            logger.info(
                "query_submitted",
                query_id=str(record.id),
                snowflake_query_id=sfqid,
            )
        except Exception as e:
            record.status = QueryStatus.FAILED
            record.error_message = str(e)
            record.completed_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            self._session.add(record)
            await self._session.commit()
            await self._session.refresh(record)
            logger.error(
                "query_submit_failed",
                query_id=str(record.id),
                error=str(e),
            )

        return record

    async def get_query_status(self, query_id: uuid.UUID) -> QueryRecord | None:
        """Get current status, polling warehouse if still running."""
        record = await self._session.get(QueryRecord, query_id)
        if record is None:
            return None

        # Only poll warehouse if the query is still in-flight
        if record.status == QueryStatus.RUNNING and record.snowflake_query_id:
            result = await self._warehouse.get_query_status(record.snowflake_query_id)
            if result.status == WarehouseQueryStatus.SUCCESS:
                record.status = QueryStatus.SUCCESS
                record.result_rows = result.rows
                record.row_count = result.row_count
                record.completed_at = datetime.utcnow()
            elif result.status == WarehouseQueryStatus.FAILED:
                record.status = QueryStatus.FAILED
                record.error_message = result.error_message
                record.completed_at = datetime.utcnow()
            # PENDING/RUNNING — no update needed

            record.updated_at = datetime.utcnow()
            self._session.add(record)
            await self._session.commit()
            await self._session.refresh(record)

        return record

    async def recover_pending_queries(self) -> int:
        """Reconcile PENDING and RUNNING queries on startup. Returns count recovered."""
        statement = select(QueryRecord).where(
            QueryRecord.status.in_([QueryStatus.PENDING, QueryStatus.RUNNING])
        )
        results = await self._session.exec(statement)
        records = results.all()

        if not records:
            logger.info("recovery_no_pending_queries")
            return 0

        recovered = 0
        for record in records:
            try:
                if record.status == QueryStatus.PENDING:
                    await self._recover_pending(record)
                elif record.status == QueryStatus.RUNNING:
                    await self._recover_running(record)
                recovered += 1
            except Exception as e:
                logger.error(
                    "recovery_failed",
                    query_id=str(record.id),
                    error=str(e),
                )
                record.status = QueryStatus.FAILED
                record.error_message = f"Recovery failed: {e}"
                record.completed_at = datetime.utcnow()
                record.updated_at = datetime.utcnow()
                self._session.add(record)

        await self._session.commit()
        logger.info("recovery_complete", total=len(records), recovered=recovered)
        return recovered

    async def _recover_pending(self, record: QueryRecord) -> None:
        """Re-submit a query that was persisted but never reached the warehouse."""
        logger.info("recovery_resubmit", query_id=str(record.id))
        sfqid = await self._warehouse.submit_query(record.sql)
        record.snowflake_query_id = sfqid
        record.status = QueryStatus.RUNNING
        record.started_at = datetime.utcnow()
        record.updated_at = datetime.utcnow()
        self._session.add(record)

    async def _recover_running(self, record: QueryRecord) -> None:
        """Reconcile a query that was submitted but whose final status we missed."""
        if not record.snowflake_query_id:
            # No warehouse ID — treat as pending and re-submit
            await self._recover_pending(record)
            return

        logger.info(
            "recovery_poll",
            query_id=str(record.id),
            snowflake_query_id=record.snowflake_query_id,
        )
        result = await self._warehouse.get_query_status(record.snowflake_query_id)

        if result.status == WarehouseQueryStatus.SUCCESS:
            record.status = QueryStatus.SUCCESS
            record.result_rows = result.rows
            record.row_count = result.row_count
            record.completed_at = datetime.utcnow()
        elif result.status == WarehouseQueryStatus.FAILED:
            record.status = QueryStatus.FAILED
            record.error_message = result.error_message
            record.completed_at = datetime.utcnow()
        # Still running — leave as-is

        record.updated_at = datetime.utcnow()
        self._session.add(record)
