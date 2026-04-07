"""Abstract repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TypeVar

from sqlmodel import SQLModel

T = TypeVar("T", bound=SQLModel)


class AbstractRepository(ABC):
    """Abstract repository interface for data access.

    Implement this to swap storage backends (e.g., SQL, in-memory, Redis).
    """

    @abstractmethod
    async def get(self, model: type[T], id: int) -> T | None: ...

    @abstractmethod
    async def get_all(
        self, model: type[T], *, offset: int = 0, limit: int = 100
    ) -> Sequence[T]: ...

    @abstractmethod
    async def create(self, instance: T) -> T: ...

    @abstractmethod
    async def update(self, instance: T, data: dict) -> T: ...

    @abstractmethod
    async def delete(self, instance: T) -> None: ...
