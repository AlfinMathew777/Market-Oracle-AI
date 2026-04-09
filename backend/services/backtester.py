"""Backtest engine for Market Oracle AI.

Resolves historical predictions from prediction_log against actual
yfinance price data and returns accuracy metrics broken down by
confidence band, direction, and ticker.

This is the ground-truth validator. Run it after deploying any change
to the confidence pipeline to check whether accuracy improved.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp from the database into a timezone-aware datetime."""
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts_str)
    except ValueError:
        # Fallback for timestamps without timezone info
        dt = datetime.fromisoformat(ts_str.replace("+00:00", ""))
        return dt.replace(tzinfo=timezone.utc)


async def backtest_predictions(
    ticker: Optional[str] = None,
    days: int = 30,
) -> dict:
    """Backtest prediction_log entries against actual 7-day price moves.

    Fetches up to 200 resolved-or-evaluable predictions and checks whether
    each directional call was correct after the 7-day horizon.

    Args:
        ticker: Optional ASX ticker filter.
        days:   How many days of history to backtest (look-back window).

    Returns a dict with:
        status                       — "success" | "no_predictions" | "error"
        sample_size                  — total predictions evaluated
        accuracy_pct                 — overall directional accuracy
        correct_count                — number of correct predictions
        high_confidence_accuracy_pct — accuracy when confidence ≥ 65%
        low_confidence_accuracy_pct  — accuracy when confidence < 55%
        avg_return_pct               — average actual return across all predictions
        breakdown_by_direction       — {bullish: {total, correct, accuracy_pct}, bearish: ...}
        results                      — list of individual prediction outcomes
    """
    from database import get_full_prediction_log
    try:
        import yfinance as yf
    except ImportError:
        return {"status": "error", "detail": "yfinance not installed"}

    try:
        predictions = await get_full_prediction_log(ticker=ticker, days=days, limit=200)
    except Exception as e:
        logger.error("[BACKTEST] Failed to fetch prediction log: %s", e)
        return {"status": "error", "detail": str(e)}

    # Only directional predictions (skip neutral)
    tradeable = [
        p for p in predictions
        if p.get("predicted_direction") in ("bullish", "bearish")
    ]

    if not tradeable:
        return {"status": "no_predictions", "sample_size": 0}

    now = datetime.now(timezone.utc)
    results: list[dict] = []

    for pred in tradeable:
        pred_date_str = pred.get("predicted_at", "")
        if not pred_date_str:
            continue

        try:
            pred_date = _parse_timestamp(pred_date_str)
        except Exception:
            continue

        eval_date = pred_date + timedelta(days=7)
        if eval_date > now:
            continue  # Horizon hasn't elapsed yet

        pred_ticker = pred.get("ticker", "")
        if not pred_ticker:
            continue

        try:
            hist = yf.Ticker(pred_ticker).history(
                start=pred_date.strftime("%Y-%m-%d"),
                end=(eval_date + timedelta(days=2)).strftime("%Y-%m-%d"),
            )
            if len(hist) < 2:
                continue

            entry_price = float(hist["Close"].iloc[0])
            exit_price  = float(hist["Close"].iloc[-1])
            if entry_price <= 0:
                continue

            actual_return = (exit_price - entry_price) / entry_price
            predicted_direction = pred.get("predicted_direction", "")

            correct = (
                (predicted_direction == "bullish" and actual_return > 0)
                or (predicted_direction == "bearish" and actual_return < 0)
            )

            results.append({
                "prediction_id":        pred.get("id", ""),
                "ticker":               pred_ticker,
                "predicted_direction":  predicted_direction,
                "confidence":           pred.get("confidence", 0.0),
                "predicted_at":         pred_date_str,
                "actual_return_pct":    round(actual_return * 100, 2),
                "correct":              correct,
            })
        except Exception as e:
            logger.warning("[BACKTEST] Failed to evaluate %s (%s): %s",
                           pred.get("id", "?"), pred_ticker, e)

    if not results:
        return {"status": "no_evaluable_predictions", "sample_size": 0}

    correct_count = sum(1 for r in results if r["correct"])
    accuracy      = correct_count / len(results)
    avg_return    = sum(r["actual_return_pct"] for r in results) / len(results)

    # Accuracy by confidence band
    high_conf = [r for r in results if r["confidence"] >= 0.65]
    low_conf  = [r for r in results if r["confidence"] <  0.55]
    mid_conf  = [r for r in results if 0.55 <= r["confidence"] < 0.65]

    def _band_accuracy(band: list[dict]) -> Optional[float]:
        if not band:
            return None
        return round(sum(1 for r in band if r["correct"]) / len(band) * 100, 1)

    # Breakdown by direction
    breakdown: dict = {}
    for direction in ("bullish", "bearish"):
        dir_results = [r for r in results if r["predicted_direction"] == direction]
        if dir_results:
            dir_correct = sum(1 for r in dir_results if r["correct"])
            breakdown[direction] = {
                "total":        len(dir_results),
                "correct":      dir_correct,
                "accuracy_pct": round(dir_correct / len(dir_results) * 100, 1),
            }

    return {
        "status":                        "success",
        "ticker_filter":                 ticker,
        "days":                          days,
        "sample_size":                   len(results),
        "accuracy_pct":                  round(accuracy * 100, 1),
        "correct_count":                 correct_count,
        "high_confidence_accuracy_pct":  _band_accuracy(high_conf),
        "mid_confidence_accuracy_pct":   _band_accuracy(mid_conf),
        "low_confidence_accuracy_pct":   _band_accuracy(low_conf),
        "high_confidence_count":         len(high_conf),
        "mid_confidence_count":          len(mid_conf),
        "low_confidence_count":          len(low_conf),
        "avg_return_pct":                round(avg_return, 2),
        "breakdown_by_direction":        breakdown,
        "results":                       results,
    }
