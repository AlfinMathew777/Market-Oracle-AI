"""
Backtesting API Routes
----------------------
POST /api/backtest/run             — start a backtest (background task)
GET  /api/backtest/status/{run_id} — poll progress
GET  /api/backtest/results/{run_id}— fetch completed results (paginated)
GET  /api/backtest/runs            — list recent runs
GET  /api/backtest/health          — liveness check
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from backtesting.backtest_engine import (
    BacktestConfig,
    _create_run,
    generate_run_id,
    get_run_predictions,
    get_run_status,
    init_backtest_tables,
    is_trading_day,
    run_backtest,
)
from middleware.auth import optional_api_key
from middleware.rate_limit import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtesting"])

_MAX_TICKERS = 10
_MAX_DAYS = 365


# ── Request model ──────────────────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    tickers: list[str] = Field(
        ...,
        min_length=1,
        max_length=_MAX_TICKERS,
        description="ASX tickers, e.g. ['BHP.AX', 'CBA.AX']",
    )
    start_date: str = Field(..., description="Start date YYYY-MM-DD", examples=["2025-01-01"])
    end_date: str = Field(..., description="End date YYYY-MM-DD",   examples=["2025-12-31"])
    lookback_days: int = Field(default=30, ge=10, le=90)

    @field_validator("tickers")
    @classmethod
    def normalise_tickers(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("At least one valid ticker is required")
        return cleaned

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_fmt(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be YYYY-MM-DD, got: {v!r}")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_range(cls, end: str, info) -> str:
        start = info.data.get("start_date")
        if not start:
            return end
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end,   "%Y-%m-%d")
        if e <= s:
            raise ValueError("end_date must be after start_date")
        if (e - s).days > _MAX_DAYS:
            raise ValueError(f"Date range exceeds {_MAX_DAYS}-day maximum")
        return end


# ── Helpers ────────────────────────────────────────────────────────────────────

def _count_trading_days(start_date: str, end_date: str) -> int:
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date,   "%Y-%m-%d")
    count = 0
    cur = s
    while cur <= e:
        if is_trading_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/run")
async def start_backtest(
    body: BacktestRunRequest,
    http_request: Request,
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Start a backtest run as a background task and return the run_id immediately.

    Poll /api/backtest/status/{run_id} for progress.
    Fetch /api/backtest/results/{run_id} when status is 'completed'.

    Backtests are CPU- and network-intensive; rate limited to 10 req/min.
    """
    rate_limiter.check(http_request, endpoint_type="llm", api_key=api_key)

    await init_backtest_tables()

    config = BacktestConfig(
        tickers=tuple(body.tickers),
        start_date=body.start_date,
        end_date=body.end_date,
        lookback_days=body.lookback_days,
    )

    # Pre-create the DB row so the run_id is safe to return before the task runs.
    run_id = generate_run_id()
    total_steps = _count_trading_days(body.start_date, body.end_date) * len(body.tickers)
    await _create_run(run_id, config, total_steps)

    # Launch background task — run_backtest won't re-create the row (caller_pre_created=True)
    async def _task() -> None:
        try:
            await run_backtest(config, run_id=run_id)
        except Exception as exc:
            logger.error("Background backtest %s failed: %s", run_id, exc)

    asyncio.create_task(_task())

    return {
        "status": "success",
        "data": {
            "run_id": run_id,
            "status": "running",
            "tickers": body.tickers,
            "start_date": body.start_date,
            "end_date": body.end_date,
            "total_steps": total_steps,
            "message": (
                f"Backtest started. "
                f"Poll /api/backtest/status/{run_id} for progress."
            ),
        },
    }


@router.get("/status/{run_id}")
async def backtest_status(
    run_id: str,
    http_request: Request,
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Poll the progress of a running backtest.

    Progress counter updates every 50 predictions processed, so expect
    ~1-2 second granularity for a typical 252-day × 5-ticker run.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)

    row = await get_run_status(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")

    progress = row.get("progress", 0) or 0
    total    = row.get("total_steps", 0) or 0
    pct      = round(progress / total * 100, 1) if total > 0 else 0.0

    config_data: dict = {}
    try:
        config_data = json.loads(row.get("config") or "{}")
    except Exception:
        pass

    return {
        "status": "success",
        "data": {
            "run_id":       run_id,
            "status":       row["status"],
            "progress":     progress,
            "total":        total,
            "progress_pct": pct,
            "started_at":   row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "config":       config_data,
            "error":        row.get("error"),
        },
    }


@router.get("/results/{run_id}")
async def backtest_results(
    run_id: str,
    http_request: Request,
    page:      int           = Query(1,   ge=1,  description="Page (1-based)"),
    page_size: int           = Query(100, ge=1, le=500),
    ticker:    Optional[str] = Query(None, description="Filter by ticker"),
    api_key: Optional[str]   = Depends(optional_api_key),
):
    """
    Return completed backtest metrics and paginated predictions.

    Returns 200 with status='running' if the backtest is still in progress —
    the caller should keep polling /status until complete.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)

    row = await get_run_status(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")

    if row["status"] == "running":
        progress = row.get("progress", 0) or 0
        total    = row.get("total_steps", 0) or 0
        return {
            "status": "success",
            "data": {
                "run_id":   run_id,
                "status":   "running",
                "progress": progress,
                "total":    total,
                "message":  "Backtest still in progress — check /status endpoint",
            },
        }

    if row["status"] == "failed":
        return {
            "status": "error",
            "data": {
                "run_id": run_id,
                "status": "failed",
                "error":  row.get("error"),
            },
        }

    metrics: dict = {}
    try:
        raw = row.get("metrics")
        if raw:
            metrics = json.loads(raw)
    except Exception:
        pass

    config_data: dict = {}
    try:
        raw_cfg = row.get("config")
        if raw_cfg:
            config_data = json.loads(raw_cfg)
    except Exception:
        pass

    predictions, total_count = await get_run_predictions(
        run_id, page=page, page_size=page_size, ticker=ticker
    )

    return {
        "status": "success",
        "data": {
            "run_id":       run_id,
            "status":       "completed",
            "completed_at": row.get("completed_at"),
            "config":       config_data,
            "metrics":      metrics,
            "predictions":  predictions,
            "pagination": {
                "page":      page,
                "page_size": page_size,
                "total":     total_count,
                "pages":     (total_count + page_size - 1) // page_size,
            },
        },
    }


@router.get("/runs")
async def list_runs(
    http_request: Request,
    limit:   int           = Query(20, ge=1, le=100),
    api_key: Optional[str] = Depends(optional_api_key),
):
    """List recent backtest runs, newest first."""
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)

    await init_backtest_tables()

    import aiosqlite
    from database import DB_PATH as _DB_PATH

    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
        async with db.execute(
            """SELECT
                   run_id, status, started_at, completed_at,
                   progress, total_steps, error,
                   json_extract(config, '$.tickers')    as tickers_json,
                   json_extract(config, '$.start_date') as start_date,
                   json_extract(config, '$.end_date')   as end_date
               FROM backtest_runs
               ORDER BY started_at DESC
               LIMIT ?""",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()

    for row in rows:
        try:
            row["tickers"] = json.loads(row.pop("tickers_json") or "[]")
        except Exception:
            row["tickers"] = []

    return {"status": "success", "data": rows}


@router.get("/health")
async def health():
    return {"status": "ok", "service": "backtest"}
