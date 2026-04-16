"""
Shared pytest fixtures for Market Oracle AI backend tests.

Design principles:
- Every test gets a fresh in-memory DB — no production data ever touched.
- External services (yfinance, Anthropic, FRED) are always mocked.
- System state (kill switch) is restored after each test.
- The FastAPI TestClient uses a minimal app — no background tasks, no LLM init.
"""

import os
import sys
from datetime import datetime, timezone
from typing import AsyncIterator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ── Path setup ─────────────────────────────────────────────────────────────────
# Ensure `from database import ...`, `from monitoring.alerts import ...` etc. work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force test environment before any app module is imported
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("PAPER_MODE", "true")


# ── DB isolation ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def isolated_db(tmp_path, monkeypatch) -> AsyncIterator[str]:
    """
    Provide a fresh SQLite database for each test.

    - Patches `database.DB_PATH` to a temp file so production data is untouched.
    - Resets `_initialized` so `init_db()` runs the full DDL in the temp DB.
    - Yields the db path string for tests that need to verify DB state directly.
    """
    import database

    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(database, "_initialized", False)

    await database.init_db()
    yield db_path


# ── Lightweight TestClient ─────────────────────────────────────────────────────

@pytest.fixture
def admin_client(isolated_db) -> Generator:
    """
    Minimal FastAPI TestClient with only the admin router mounted.

    Skips the full production lifespan (no LLM init, no AIS stream, no Redis).
    API key auth is automatically disabled — `API_KEY` env var is unset in tests.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.admin import router as admin_router

    mini_app = FastAPI()
    mini_app.include_router(admin_router)

    with TestClient(mini_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def health_client() -> Generator:
    """Minimal TestClient exposing only the /api/health endpoint."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini_app = FastAPI()

    @mini_app.get("/api/health")
    async def _health():
        from config.environment import ENV
        return {
            "status": "operational",
            "environment": ENV,
            "data_sources": {},
            "live_data_sources": "0/0",
            "demo_ready": False,
            "response_time_ms": 0.0,
            "llm_circuits": {},
        }

    with TestClient(mini_app) as client:
        yield client


# ── Sample data ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_prediction() -> dict:
    """
    Minimal prediction_log row dict.

    All fields required by `validate_prediction` and `get_pending_validations`
    are present. Predicted 48 hours ago so it's eligible for 24h validation.
    """
    return {
        "id": "test-pred-001",
        "ticker": "BHP.AX",
        "predicted_direction": "bullish",
        "confidence": 0.72,
        "predicted_at": "2026-04-15T02:00:00+00:00",   # ~48h ago
        "primary_reason": "Iron ore demand surge",
        "bhp_price_at_prediction": 45.20,
        "agent_bullish": 28,
        "agent_bearish": 12,
        "agent_neutral": 10,
    }


@pytest.fixture
def sample_alert() -> dict:
    """Minimal alert row dict."""
    return {
        "alert_type": "ACCURACY_DROP",
        "severity": "critical",
        "message": "7-day accuracy dropped to 45% (9/20)",
        "context": '{"hit_rate_pct": 45.0, "correct": 9, "total": 20, "days": 7}',
    }


# ── External service mocks ─────────────────────────────────────────────────────

@pytest.fixture
def mock_yfinance():
    """
    Patch yfinance.Ticker globally so no real HTTP calls are made.

    The mock returns a DataFrame-like history with a single Close price row
    at 46.10 — representing a +2% move from the sample entry price of 45.20.
    """
    import pandas as pd

    mock_hist = pd.DataFrame(
        {"Close": [46.10]},
        index=pd.to_datetime(["2026-04-16"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = mock_hist
    mock_ticker.fast_info.last_price = 46.10

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock:
        yield mock


@pytest.fixture
def mock_yfinance_rate_limited():
    """Patch yfinance to raise a rate-limit error on first call, then succeed."""
    import pandas as pd

    call_count = {"n": 0}
    mock_hist = pd.DataFrame(
        {"Close": [46.10]},
        index=pd.to_datetime(["2026-04-16"]),
    )

    def history_side_effect(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise Exception("Too many requests (429)")
        return mock_hist

    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = history_side_effect

    with patch("yfinance.Ticker", return_value=mock_ticker):
        yield call_count


# ── System state reset ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_system_state():
    """
    Restore kill switch state after every test.

    autouse=True means this runs automatically — no test can accidentally leave
    the kill switch active and pollute subsequent tests.
    """
    import system_state

    original_enabled = system_state._signals_enabled
    original_reason = system_state._kill_switch_reason
    original_activated_at = system_state._kill_switch_activated_at

    yield

    system_state._signals_enabled = original_enabled
    system_state._kill_switch_reason = original_reason
    system_state._kill_switch_activated_at = original_activated_at


# ── DB helper ──────────────────────────────────────────────────────────────────

async def insert_prediction(db_path: str, prediction: dict) -> None:
    """Helper: insert a row into prediction_log in the isolated test DB."""
    import aiosqlite

    row = {
        "id": prediction.get("id", "test-001"),
        "ticker": prediction.get("ticker", "BHP.AX"),
        "predicted_direction": prediction.get("predicted_direction", "bullish"),
        "confidence": prediction.get("confidence", 0.70),
        "predicted_at": prediction.get("predicted_at", "2026-04-15T02:00:00+00:00"),
        "primary_reason": prediction.get("primary_reason", ""),
        "bhp_price_at_prediction": prediction.get("bhp_price_at_prediction", 45.20),
        "created_at": prediction.get("created_at", datetime.now(timezone.utc).isoformat()),
    }
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO prediction_log
               (id, ticker, predicted_direction, confidence,
                predicted_at, primary_reason,
                bhp_price_at_prediction, created_at)
               VALUES (:id, :ticker, :predicted_direction, :confidence,
                       :predicted_at, :primary_reason,
                       :bhp_price_at_prediction, :created_at)""",
            row,
        )
        await db.commit()


async def insert_alert(db_path: str, alert: dict) -> int:
    """Helper: insert an alert row and return its rowid."""
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            """INSERT INTO alerts (alert_type, severity, message, context, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                alert["alert_type"],
                alert["severity"],
                alert["message"],
                alert.get("context"),
                alert.get("created_at", datetime.now(timezone.utc).isoformat()),
            ),
        )
        await db.commit()
        return cur.lastrowid
