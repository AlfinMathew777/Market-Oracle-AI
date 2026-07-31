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
from services.accuracy_tracker import get_accuracy_summary, get_resolved_predictions_for_eval
from services.prediction_evaluator import evaluate_predictions
from services.failure_analyzer import analyze_failures

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


@router.get("/evaluation")
async def get_evaluation_metrics(
    http_request: Request,
    ticker: Optional[str] = Query(None, description="Filter by ASX ticker"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Return F1, precision, and recall metrics for resolved predictions.

    These metrics handle class imbalance better than simple accuracy —
    important because NEUTRAL predictions dominate low-signal periods.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)
    predictions = await get_resolved_predictions_for_eval(ticker=ticker, days=days)
    evaluation = evaluate_predictions(predictions)
    return {"success": True, "evaluation": evaluation}


@router.get("/failure-analysis")
async def get_failure_analysis(
    http_request: Request,
    ticker: Optional[str] = Query(None, description="Filter by ASX ticker"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    api_key: Optional[str] = Depends(optional_api_key),
):
    """
    Return failure pattern analysis (data flywheel report).

    Categorizes why predictions failed and surfaces actionable
    recommendations to improve prompts and signal weights.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)
    predictions = await get_resolved_predictions_for_eval(ticker=ticker, days=days)
    analysis = analyze_failures(predictions, days=days)
    return {"success": True, "analysis": analysis}


@router.get("/significance")
async def accuracy_significance(
    http_request: Request,
    ticker: str | None = Query(None, description="Filter by ASX ticker, e.g. BHP.AX"),
    days: int = Query(365, ge=30, le=730, description="Lookback window in days"),
    n_permutations: int = Query(10_000, ge=1000, le=100_000, description="Permutation count"),
    api_key: str | None = Depends(optional_api_key),
):
    """
    Permutation-test the track record: is the observed accuracy
    statistically distinguishable from an uninformed predictor?

    Shuffles predicted labels against actual labels (preserving both
    marginals) to build the null distribution, then reports the p-value.
    Stronger than a coin-flip baseline — a bullish-leaning predictor in a
    trending market scores above 50% for free; the permutation null prices
    that in.
    """
    rate_limiter.check(http_request, endpoint_type="default", api_key=api_key)
    from quant.significance import run_accuracy_significance
    result = await run_accuracy_significance(
        ticker=ticker, days=days, n_permutations=n_permutations
    )
    return {"success": "error" not in result, "significance": result}


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "accuracy_tracker"}
