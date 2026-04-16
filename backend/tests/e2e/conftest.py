"""
Shared fixtures for e2e / API contract tests.

Uses the same mini-app pattern as integration/conftest.py — mounts all
main routers without the full production lifespan.
"""

import os
import sys

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.pop("API_KEY", None)


@pytest_asyncio.fixture
async def api_client(isolated_db):
    """Full-surface async client for contract tests."""
    from routes.admin import router as admin_router
    from routes.backtest import router as backtest_router
    from routes.data import router as data_router
    from routes.simulate import router as simulate_router

    app = FastAPI()
    for router in (simulate_router, admin_router, backtest_router, data_router):
        app.include_router(router)

    # Minimal /api/health stub so contract tests don't need the full server
    @app.get("/api/health")
    async def _health():
        from queue.simulation_queue import QUEUE_ENABLED, queue as sim_queue

        queue_stats: dict = {}
        if QUEUE_ENABLED:
            try:
                queue_stats = await sim_queue.get_stats()
            except Exception:
                pass

        return {
            "status": "operational",
            "environment": "test",
            "data_sources": {},
            "live_data_sources": "0/0",
            "demo_ready": False,
            "response_time_ms": 0.0,
            "llm_circuits": {},
            "queue": queue_stats or {"enabled": False},
        }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
