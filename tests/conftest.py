"""Shared test fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from query_scheduler.app import app


@pytest.fixture
async def client():
    """Async test client using httpx."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
