"""Abstract warehouse interface for external data platform queries."""

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass


class WarehouseQueryStatus(enum.StrEnum):
    """Status reported by the warehouse for a running query."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class WarehouseQueryResult:
    """Result of polling a warehouse query."""

    status: WarehouseQueryStatus
    rows: list[dict] | None = None
    error_message: str | None = None
    row_count: int | None = None


class AbstractWarehouse(ABC):
    """Interface for submitting and polling async queries against a data warehouse."""

    @abstractmethod
    async def submit_query(self, sql: str) -> str:
        """Submit SQL for async execution. Returns the warehouse-native query ID."""

    @abstractmethod
    async def get_query_status(self, warehouse_query_id: str) -> WarehouseQueryResult:
        """Poll the warehouse for current query status and results if complete."""

    @abstractmethod
    async def close(self) -> None:
        """Clean up connections."""
