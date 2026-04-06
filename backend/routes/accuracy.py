"""
Accuracy Tracking API Route
---------------------------
Exposes prediction accuracy metrics and track record.
Read-only — uses optional auth (open in dev, required in production).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from middleware.auth import optional_api_key
from middleware.rate_limit import rate_limiter
from services.accuracy_tracker import get_accuracy_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])


@router.get("/summary")
async def accuracy_summary(
    http_request: Request,
    ticker: Optional[str] = Query(None, description="Filter by ASX ticker, e.g. BHP.AX"),
    direction: Optional[str] = Query(None, description="Filter by direction: Bullish / Bearish"),
    days: int = Query(90, ge=1, le=365, description="Lookback window in days"),
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Return prediction accuracy metrics for the Reasoning Synthesizer.

    Optionally filtered by ticker and/or direction over a rolling time window.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)
    return await get_accuracy_summary(ticker=ticker, direction=direction, days=days)


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "accuracy_tracker"}
