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
    result = _executor.generate_execution_plan(request)

    if result is None:
        raise HTTPException(
            status_code=422,
            detail=f"Signal not actionable: {request.recommendation} / {request.direction}",
        )

    return result


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "trade_executor",
        "auth_required": True,
        "rate_limit": "10 requests/minute",
    }
