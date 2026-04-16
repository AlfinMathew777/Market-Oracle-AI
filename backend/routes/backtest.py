"""
Backtesting API Routes
----------------------
POST /api/backtest/run        — start a backtest (background task)
GET  /api/backtest/status/{run_id} — poll progress
GET  /api/backtest/results/{run_id} — fetch completed results (paginated)
GET  /api/backtest/runs       — list recent runs
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from backtesting.backtest_engine import (
    BacktestConfig,
    get_run_predictions,
    get_run_status,
    init_backtest_tables,
    run_backtest,
)
from middleware.auth import optional_api_key
from middleware.rate_limit import rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtesting"])

# Maximum tickers and date range allowed per request (prevent abuse)
_MAX_TICKERS = 10
_MAX_DAYS = 365


# ── Request / response models ──────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    tickers: list[str] = Field(
        ...,
        min_length=1,
        max_length=_MAX_TICKERS,
        description="ASX tickers to backtest, e.g. ['BHP.AX', 'CBA.AX']",
    )
    start_date: str = Field(
        ...,
        description="Start date YYYY-MM-DD",
        examples=["2025-01-01"],
    )
    end_date: str = Field(
        ...,
        description="End date YYYY-MM-DD",
        examples=["2025-12-31"],
    )
    lookback_days: int = Field(
        default=30,
        ge=10,
        le=90,
        description="Indicator lookback window in days",
    )

    @field_validator("tickers")
    @classmethod
    def validate_tickers(cls, v: list[str]) -> list[str]:
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("At least one ticker is required")
        return cleaned

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Date must be YYYY-MM-DD, got: {v!r}")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, end: str, info) -> str:
        start = info.data.get("start_date")
        if not start:
            return end
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")
        if end_dt <= start_dt:
            raise ValueError("end_date must be after start_date")
        if (end_dt - start_dt).days > _MAX_DAYS:
            raise ValueError(f"Date range exceeds maximum of {_MAX_DAYS} days")
        return end


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/run")
async def start_backtest(
    body: BacktestRunRequest,
    http_request: Request,
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Start a backtest run as a background task.

    Returns immediately with the run_id. Poll /api/backtest/status/{run_id}
    for progress, then fetch /api/backtest/results/{run_id} when complete.

    Rate limited to 5 requests/minute — backtests are CPU and network intensive.
    """
    rate_limiter.check(http_request, endpoint_type="llm", api_key=api_key)

    await init_backtest_tables()

    config = BacktestConfig(
        tickers=tuple(body.tickers),
        start_date=body.start_date,
        end_date=body.end_date,
        lookback_days=body.lookback_days,
    )

    # Run as a background asyncio task so the response returns immediately.
    # Errors inside the task are persisted to backtest_runs.error and won't
    # crash the server.
    async def _task():
        try:
            await run_backtest(config)
        except Exception as exc:
            logger.error("Background backtest failed: %s", exc)

    # We need the run_id before the task starts.  run_backtest generates one
    # internally, so we pre-generate it here and pass it in.
    import uuid
    from backtesting.backtest_engine import (
        _create_run,
        _fail_run,
        init_backtest_tables as _init,
    )
    from datetime import timedelta

    await _init()

    run_id = f"bt_{uuid.uuid4().hex[:12]}"

    # Calculate expected total steps so status polling shows real progress.
    from backtesting.backtest_engine import is_trading_day

    start_dt = datetime.strptime(body.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(body.end_date, "%Y-%m-%d")
    trading_days = 0
    cursor = start_dt
    while cursor <= end_dt:
        if is_trading_day(cursor):
            trading_days += 1
        cursor += timedelta(days=1)

    total_steps = trading_days * len(body.tickers)
    await _create_run(run_id, config, total_steps)

    async def _run_with_id():
        from backtesting.backtest_engine import (
            _bulk_save_predictions,
            _complete_run,
            _fail_run as _fail,
            _generate_signal,
            _determine_outcome,
            _update_progress,
            calculate_metrics,
            fetch_historical_data,
            BacktestPrediction,
        )
        import pandas as pd

        start_dt_ = datetime.strptime(body.start_date, "%Y-%m-%d")
        end_dt_ = datetime.strptime(body.end_date, "%Y-%m-%d")

        days: list[datetime] = []
        cur = start_dt_
        while cur <= end_dt_:
            if is_trading_day(cur):
                days.append(cur)
            cur += timedelta(days=1)

        try:
            ticker_data: dict[str, pd.DataFrame] = {}
            for i, ticker in enumerate(config.tickers):
                try:
                    df = await fetch_historical_data(
                        ticker, body.start_date, body.end_date
                    )
                    ticker_data[ticker] = df
                except Exception as exc:
                    logger.warning("Skipping %s: %s", ticker, exc)
                if i < len(config.tickers) - 1:
                    await asyncio.sleep(1.5)

            if not ticker_data:
                raise RuntimeError("No ticker data fetched")

            predictions: list[BacktestPrediction] = []
            step = 0

            for ticker, df in ticker_data.items():
                for day in days:
                    day_ts = pd.Timestamp(day)
                    past = df[df.index < day_ts]
                    if len(past) < 20:
                        step += 1
                        continue
                    day_row = df[df.index == day_ts]
                    if day_row.empty:
                        step += 1
                        continue
                    entry_price = float(day_row["Open"].iloc[0])
                    future = df[df.index > day_ts]
                    if future.empty:
                        step += 1
                        continue
                    exit_price = float(future["Close"].iloc[0])
                    change_pct = (exit_price - entry_price) / entry_price * 100.0

                    direction, confidence = _generate_signal(
                        df, day_ts, config.lookback_days
                    )
                    outcome = _determine_outcome(direction, change_pct)

                    predictions.append(
                        BacktestPrediction(
                            date=day.strftime("%Y-%m-%d"),
                            ticker=ticker,
                            direction=direction,
                            confidence=confidence,
                            entry_price=round(entry_price, 4),
                            exit_price=round(exit_price, 4),
                            change_pct=round(change_pct, 4),
                            outcome=outcome,
                        )
                    )
                    step += 1
                    if step % 50 == 0:
                        await _update_progress(run_id, step)
                        await asyncio.sleep(0)

            metrics = calculate_metrics(predictions)
            await _bulk_save_predictions(run_id, predictions)
            await _complete_run(run_id, metrics)
            logger.info(
                "Backtest %s complete: %d predictions, hit_rate=%.1f%%",
                run_id, metrics.total_predictions, metrics.hit_rate * 100,
            )

        except Exception as exc:
            logger.error("Backtest %s failed: %s", run_id, exc, exc_info=True)
            await _fail(run_id, str(exc))

    asyncio.create_task(_run_with_id())

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
                f"Backtest started. Poll /api/backtest/status/{run_id} "
                "for progress."
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
    Poll the status and progress of a backtest run.

    Progress is updated every 50 predictions — expect ~1-2 second granularity
    for a typical 252-day × 5-ticker run.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)

    row = await get_run_status(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    config_data = {}
    try:
        config_data = json.loads(row["config"])
    except Exception:
        pass

    progress = row.get("progress", 0)
    total = row.get("total_steps", 0)
    pct = round(progress / total * 100, 1) if total > 0 else 0

    return {
        "status": "success",
        "data": {
            "run_id": run_id,
            "status": row["status"],
            "progress": progress,
            "total": total,
            "progress_pct": pct,
            "started_at": row.get("started_at"),
            "completed_at": row.get("completed_at"),
            "config": config_data,
            "error": row.get("error"),
        },
    }


@router.get("/results/{run_id}")
async def backtest_results(
    run_id: str,
    http_request: Request,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(100, ge=1, le=500, description="Results per page"),
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Fetch completed backtest results.

    Predictions are paginated — use *page* and *page_size* for large runs.
    Optionally filter to a single ticker with the *ticker* query param.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)

    row = await get_run_status(run_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    if row["status"] == "running":
        return {
            "status": "success",
            "data": {
                "run_id": run_id,
                "status": "running",
                "progress": row.get("progress", 0),
                "total": row.get("total_steps", 0),
                "message": "Backtest still in progress — check status endpoint",
            },
        }

    if row["status"] == "failed":
        return {
            "status": "error",
            "data": {
                "run_id": run_id,
                "status": "failed",
                "error": row.get("error"),
            },
        }

    # Parse stored metrics
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
            "run_id": run_id,
            "status": "completed",
            "completed_at": row.get("completed_at"),
            "config": config_data,
            "metrics": metrics,
            "predictions": predictions,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "pages": (total_count + page_size - 1) // page_size,
            },
        },
    }


@router.get("/runs")
async def list_runs(
    http_request: Request,
    limit: int = Query(20, ge=1, le=100, description="Max runs to return"),
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
            """SELECT run_id, status, started_at, completed_at,
                      progress, total_steps, error,
                      json_extract(config, '$.tickers') as tickers_json,
                      json_extract(config, '$.start_date') as start_date,
                      json_extract(config, '$.end_date') as end_date
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
