"""
Shared fixtures for Market Oracle AI integration tests.

Design:
- Mini FastAPI apps mount only the routers under test — no full lifespan startup,
  no LLM init, no AIS stream, no Redis requirement.
- Every test gets an isolated SQLite DB via the parent conftest's `isolated_db`.
- Auth is bypassed by leaving API_KEY unset (require_api_key is a no-op when unset).
- System state is restored by the parent conftest's autouse `reset_system_state`.
"""

import os
import sys

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Keep API_KEY unset so require_api_key becomes a no-op in all integration tests
os.environ.pop("API_KEY", None)


def _make_app(*routers) -> FastAPI:
    """Create a minimal FastAPI app with only the given routers mounted."""
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return app


@pytest_asyncio.fixture
async def admin_async_client(isolated_db):
    """AsyncClient backed by a mini app exposing only admin routes."""
    from routes.admin import router as admin_router

    app = _make_app(admin_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def simulate_async_client(isolated_db):
    """AsyncClient backed by a mini app exposing simulate + admin routes."""
    from routes.admin import router as admin_router
    from routes.simulate import router as simulate_router

    app = _make_app(simulate_router, admin_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def backtest_async_client(isolated_db):
    """AsyncClient backed by a mini app exposing only backtest routes."""
    from routes.backtest import router as backtest_router

    app = _make_app(backtest_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def full_async_client(isolated_db):
    """
    AsyncClient that mounts all main routers — for cross-route integration tests.

    Skips the heavy lifespan (no LLM init, no Redis, no AIS stream) by using
    a plain FastAPI() instead of the production server app.
    """
    from routes.admin import router as admin_router
    from routes.backtest import router as backtest_router
    from routes.data import router as data_router
    from routes.simulate import router as simulate_router

    app = _make_app(simulate_router, admin_router, backtest_router, data_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
