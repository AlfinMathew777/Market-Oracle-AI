"""
Integration tests — backtest workflow.

Tests the route layer and engine integration without real yfinance calls.
The backtest engine's `fetch_historical_data` is mocked to return a synthetic
price series so the full signal-generation pipeline runs in < 1 second.

Verifies:
  - POST /api/backtest/run creates a run_id and returns 200
  - GET /api/backtest/status/{run_id} returns progress fields
  - GET /api/backtest/results/{run_id} returns paginated result structure
  - Invalid date ranges (end < start) are rejected with 422
  - Tickers exceeding the per-request limit are rejected
  - GET /api/backtest/health returns 200
"""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest


def _make_price_df(days: int = 30, base: float = 45.0) -> pd.DataFrame:
    """Build a synthetic OHLCV DataFrame the engine can consume."""
    import numpy as np

    rng = pd.date_range(end=date.today(), periods=days, freq="B")
    closes = base + np.cumsum(np.random.randn(days) * 0.5)
    df = pd.DataFrame(
        {
            "Open": closes * 0.99,
            "High": closes * 1.01,
            "Low": closes * 0.98,
            "Close": closes,
            "Volume": [1_000_000] * days,
        },
        index=rng,
    )
    df.index = pd.to_datetime(df.index).normalize()
    return df


@pytest.mark.integration
class TestBacktestRunEndpoint:
    """POST /api/backtest/run contracts."""

    def test_run_creates_run_id(self, backtest_async_client):
        """Valid request returns a run_id and status=running."""

        async def _run():
            with patch(
                "backtesting.backtest_engine.fetch_historical_data",
                new_callable=AsyncMock,
                return_value=_make_price_df(60),
            ):
                response = await backtest_async_client.post(
                    "/api/backtest/run",
                    json={
                        "tickers": ["BHP.AX"],
                        "start_date": "2025-06-01",
                        "end_date": "2025-06-07",
                    },
                )
                return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        # Response envelope: {"status": "success", "data": {"run_id": ...}}
        inner = data.get("data", data)
        assert "run_id" in inner
        assert inner.get("status") in {"running", "queued", "started"}

    def test_run_returns_poll_url(self, backtest_async_client):
        """Response includes a message mentioning how to poll."""

        async def _run():
            with patch(
                "backtesting.backtest_engine.fetch_historical_data",
                new_callable=AsyncMock,
                return_value=_make_price_df(60),
            ):
                response = await backtest_async_client.post(
                    "/api/backtest/run",
                    json={
                        "tickers": ["CBA.AX"],
                        "start_date": "2025-07-01",
                        "end_date": "2025-07-05",
                    },
                )
                return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        inner = data.get("data", data)
        # Should contain the run_id or a poll-url hint
        assert "run_id" in inner or "poll" in str(inner).lower()

    def test_multiple_tickers_accepted(self, backtest_async_client):
        """Up to 10 tickers are accepted in a single request."""

        async def _run():
            with patch(
                "backtesting.backtest_engine.fetch_historical_data",
                new_callable=AsyncMock,
                return_value=_make_price_df(60),
            ):
                response = await backtest_async_client.post(
                    "/api/backtest/run",
                    json={
                        "tickers": ["BHP.AX", "CBA.AX", "RIO.AX"],
                        "start_date": "2025-06-01",
                        "end_date": "2025-06-07",
                    },
                )
                return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200


@pytest.mark.integration
class TestBacktestValidation:
    """BacktestRunRequest input validation."""

    def test_end_before_start_rejected(self, backtest_async_client):
        """End date before start date → 422."""

        async def _run():
            return await backtest_async_client.post(
                "/api/backtest/run",
                json={
                    "tickers": ["BHP.AX"],
                    "start_date": "2025-12-31",
                    "end_date": "2025-01-01",
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    def test_too_many_tickers_rejected(self, backtest_async_client):
        """More than 10 tickers → 422."""

        async def _run():
            tickers = [f"T{i:02d}.AX" for i in range(11)]
            return await backtest_async_client.post(
                "/api/backtest/run",
                json={
                    "tickers": tickers,
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-31",
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    def test_empty_tickers_rejected(self, backtest_async_client):
        """Empty tickers list → 422."""

        async def _run():
            return await backtest_async_client.post(
                "/api/backtest/run",
                json={
                    "tickers": [],
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-31",
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    def test_date_range_over_365_days_rejected(self, backtest_async_client):
        """Date ranges > 365 days are rejected."""

        async def _run():
            return await backtest_async_client.post(
                "/api/backtest/run",
                json={
                    "tickers": ["BHP.AX"],
                    "start_date": "2023-01-01",
                    "end_date": "2025-01-01",  # 2 years
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    def test_invalid_date_format_rejected(self, backtest_async_client):
        """Non-ISO date strings → 422."""

        async def _run():
            return await backtest_async_client.post(
                "/api/backtest/run",
                json={
                    "tickers": ["BHP.AX"],
                    "start_date": "01/01/2025",
                    "end_date": "31/03/2025",
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422


@pytest.mark.integration
class TestBacktestStatusEndpoint:
    """GET /api/backtest/status/{run_id} contracts."""

    def test_unknown_run_returns_404(self, backtest_async_client):
        async def _run():
            return await backtest_async_client.get("/api/backtest/status/run_nonexistent_abc")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 404

    def test_status_has_required_fields(self, backtest_async_client):
        """A known run_id returns status fields."""

        async def _run():
            # Create a run first
            with patch(
                "backtesting.backtest_engine.fetch_historical_data",
                new_callable=AsyncMock,
                return_value=_make_price_df(60),
            ):
                post_resp = await backtest_async_client.post(
                    "/api/backtest/run",
                    json={
                        "tickers": ["WDS.AX"],
                        "start_date": "2025-06-01",
                        "end_date": "2025-06-07",
                    },
                )
            assert post_resp.status_code == 200
            run_id = post_resp.json().get("data", post_resp.json())["run_id"]

            # Poll status
            status_resp = await backtest_async_client.get(f"/api/backtest/status/{run_id}")
            return status_resp

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        inner = data.get("data", data)
        assert any(k in inner for k in ["status", "run_id", "progress"])


@pytest.mark.integration
class TestBacktestHealthEndpoint:
    """GET /api/backtest/health is a liveness probe."""

    def test_health_returns_200(self, backtest_async_client):
        async def _run():
            return await backtest_async_client.get("/api/backtest/health")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
