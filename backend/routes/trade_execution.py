"""
Trade Execution API Route
-------------------------
Generates actionable trade parameters from prediction signals.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from agents.trade_executor import TradeExecutor
from middleware.auth import verify_api_key
from middleware.rate_limit import llm_rate_limit, rate_limiter
from models.trade_execution import TradeExecution, TradeExecutionRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trade", tags=["trade"])

_executor = TradeExecutor()


@router.post("/generate", response_model=TradeExecution)
async def generate_trade_execution(
    request: TradeExecutionRequest,
    http_request: Request,
    api_key: str = Depends(verify_api_key),
    rate_info: dict = Depends(llm_rate_limit),
) -> TradeExecution:
    """
    Generate a trade execution plan from a prediction signal.

    Returns actionable entry, exit, and risk parameters.
    Returns 422 if the signal is not actionable (HOLD/WAIT/NEUTRAL).
    """
    request = await _enrich_with_track_record(request)
    result = _executor.generate_execution_plan(request)

    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"Signal not actionable: {request.recommendation} / {request.direction}",
        )

    return result


async def _enrich_with_track_record(
    request: TradeExecutionRequest,
) -> TradeExecutionRequest:
    """
    Attach the ticker's historical win-rate so the executor can size with Kelly.

    Skipped when the caller already supplied a win-rate. Any failure (or no
    resolved history) leaves the request untouched → executor uses legacy sizing.
    """
    if request.historical_win_rate is not None:
        return request

    try:
        from services.accuracy_tracker import get_accuracy_summary

        stats = await get_accuracy_summary(ticker=request.stock_ticker, days=180)
        resolved = stats.get("resolved_predictions", 0)
        if not resolved:
            return request

        return request.model_copy(
            update={
                "historical_win_rate": stats.get("accuracy_pct", 0.0),
                "historical_sample_size": resolved,
            }
        )
    except Exception as exc:  # noqa: BLE001 — sizing must never break execution
        logger.warning("Track-record enrichment failed for %s: %s", request.stock_ticker, exc)
        return request


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "trade_executor",
        "auth_required": True,
        "rate_limit": "10 requests/minute",
    }
