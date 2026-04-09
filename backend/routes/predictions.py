"""Prediction log API routes — public track record endpoints."""

from fastapi import APIRouter, Query
from typing import Optional
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.get("/history")
async def get_prediction_history(
    ticker: Optional[str] = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
):
    """GET /api/predictions/history — full prediction log with outcomes."""
    from database import get_full_prediction_log
    rows = await get_full_prediction_log(ticker=ticker, days=days, limit=limit)
    return {"status": "success", "data": rows, "count": len(rows)}


@router.get("/accuracy")
async def get_accuracy_stats(
    ticker: Optional[str] = Query(default=None),
    days: int = Query(default=365, ge=1, le=3650),
):
    """GET /api/predictions/accuracy — detailed accuracy stats."""
    from database import get_detailed_accuracy_stats
    stats = await get_detailed_accuracy_stats(ticker=ticker, days=days)
    return {"status": "success", "data": stats}


@router.post("/log")
async def log_prediction(body: dict):
    """POST /api/predictions/log — manually log a prediction (used internally)."""
    from database import save_prediction_log
    try:
        await save_prediction_log(
            simulation_id=body.get("simulation_id", ""),
            ticker=body.get("ticker", ""),
            direction=body.get("direction", "NEUTRAL"),
            confidence=float(body.get("confidence", 0)),
            primary_reason=body.get("trigger_event", "") or body.get("primary_reason", ""),
            market_ctx={
                "iron_ore_price": body.get("iron_ore_price"),
                "audusd_rate":    body.get("audusd_rate"),
                "brent_price":    body.get("brent_price"),
                "ticker_price":   body.get("ticker_price"),
            },
            agent_bullish=body.get("agent_bullish", 0),
            agent_bearish=body.get("agent_bearish", 0),
            agent_neutral=body.get("agent_neutral", 0),
            trend_label=body.get("trend_label"),
        )
        return {"status": "success"}
    except Exception as e:
        logger.error("Manual log_prediction failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/backtest")
async def run_backtest(
    ticker: Optional[str] = Query(default=None, description="Filter to a specific ASX ticker"),
    days: int = Query(default=30, ge=1, le=365, description="Look-back window in days"),
):
    """GET /api/predictions/backtest — backtest historical predictions against actual prices.

    Resolves up to 200 directional predictions from prediction_log against
    yfinance price data. Returns accuracy by confidence band and direction.

    Example: GET /api/predictions/backtest?ticker=BHP.AX&days=60
    """
    from services.backtester import backtest_predictions
    try:
        result = await asyncio.wait_for(
            backtest_predictions(ticker=ticker, days=days),
            timeout=60.0,
        )
        return {"status": "success", "data": result}
    except asyncio.TimeoutError:
        logger.warning("Backtest timed out after 60s")
        return {"status": "error", "detail": "Backtest timed out — try a shorter days window"}
    except Exception as e:
        logger.error("Backtest failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/admin/fix-data")
async def fix_prediction_data():
    """POST /api/predictions/admin/fix-data — backfill excluded_from_stats on garbage predictions.

    Safe to call multiple times. Marks low-confidence predictions as excluded,
    then resolves any pending predictions whose 7-day horizon has elapsed.
    Returns counts of rows updated.
    """
    from database import mark_existing_garbage_predictions
    from services.prediction_resolver import auto_resolve_pending_predictions
    try:
        marked = await mark_existing_garbage_predictions()
        resolved = await asyncio.wait_for(
            auto_resolve_pending_predictions(limit=200),
            timeout=120.0,
        )
        return {
            "status": "success",
            "garbage_marked": marked,
            "predictions_resolved": resolved,
        }
    except asyncio.TimeoutError:
        return {"status": "partial", "detail": "Resolution timed out — garbage marking may still have applied"}
    except Exception as e:
        logger.error("fix-data failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/calibration")
async def get_calibration(
    ticker: Optional[str] = Query(default=None),
    days: int = Query(default=90, ge=7, le=365),
):
    """GET /api/predictions/calibration — stated confidence vs actual accuracy per bucket.

    Shows whether the system is over- or under-confident in each confidence range.
    """
    from services.confidence_calibrator import get_calibration_stats
    try:
        stats = await get_calibration_stats(ticker=ticker, days=days)
        return {"status": "success", "data": stats}
    except Exception as e:
        logger.error("Calibration stats failed: %s", e)
        return {"status": "error", "detail": str(e)}
