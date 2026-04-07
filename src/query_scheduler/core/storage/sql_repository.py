"""Concrete SQLModel repository implementation."""

from collections.abc import Sequence
from typing import TypeVar

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from query_scheduler.core.database import get_session
from query_scheduler.core.storage.repository import AbstractRepository

T = TypeVar("T", bound=SQLModel)


class SQLModelRepository(AbstractRepository):
    """Repository backed by SQLModel async sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, model: type[T], id: int) -> T | None:
        return await self._session.get(model, id)

    async def get_all(
        self, model: type[T], *, offset: int = 0, limit: int = 100
    ) -> Sequence[T]:
        statement = select(model).offset(offset).limit(limit)
        results = await self._session.exec(statement)
        return results.all()

    async def create(self, instance: T) -> T:
        self._session.add(instance)
        await self._session.commit()
        await self._session.refresh(instance)
        return instance

    async def update(self, instance: T, data: dict) -> T:
        for key, value in data.items():
            if value is not None:
                setattr(instance, key, value)
        self._session.add(instance)
        await self._session.commit()
        await self._session.refresh(instance)
        return instance

    async def delete(self, instance: T) -> None:
        await self._session.delete(instance)
        await self._session.commit()


_repository: SQLModelRepository | None = None


async def get_repository() -> SQLModelRepository:
    """Return a singleton repository instance.

    Uses get_session() to obtain the current async session.
    The singleton is lazily initialized on first call.
    """
    global _repository
    if _repository is None:
        session_gen = get_session()
        session = await session_gen.__anext__()
        _repository = SQLModelRepository(session)
    return _repository


def reset_repository() -> None:
    """Reset the singleton (useful for testing)."""
    global _repository
    _repository = None
