"""Prediction log API routes — public track record endpoints."""

from fastapi import APIRouter, Query
from typing import Optional
import logging

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
):
    """GET /api/predictions/accuracy — detailed accuracy stats."""
    from database import get_detailed_accuracy_stats
    stats = await get_detailed_accuracy_stats(ticker=ticker)
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
