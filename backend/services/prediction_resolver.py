"""
Auto-resolver for prediction_log entries.

Runs in the hourly background task. Finds predictions where the 7-day
evaluation horizon has elapsed and resolves them against actual yfinance
price data. Writes actual_direction, actual_price_change_pct, and
prediction_correct back to prediction_log.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_HORIZON_DAYS = 7  # Number of days after prediction to evaluate outcome


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 timestamp into a timezone-aware datetime."""
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        dt = datetime.fromisoformat(ts_str.split("+")[0].split("Z")[0])
        return dt.replace(tzinfo=timezone.utc)


def _actual_direction(change_pct: float) -> str:
    if change_pct > 0.5:
        return "bullish"
    elif change_pct < -0.5:
        return "bearish"
    return "neutral"


async def auto_resolve_pending_predictions(limit: int = 50) -> int:
    """
    Resolve prediction_log entries where the 7-day horizon has elapsed.

    For each unresolved prediction older than _HORIZON_DAYS, fetches the
    actual price at prediction date and _HORIZON_DAYS later via yfinance,
    then writes the outcome back to prediction_log.

    Returns the number of predictions successfully resolved.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — skipping auto-resolution")
        return 0

    from database import get_db, init_db, update_prediction_resolution

    try:
        await init_db()
    except Exception as e:
        logger.error("auto_resolve: DB init failed: %s", e)
        return 0

    cutoff = (datetime.now(timezone.utc) - timedelta(days=_HORIZON_DAYS)).isoformat()

    try:
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT id, ticker, predicted_direction, confidence, predicted_at
                   FROM prediction_log
                   WHERE prediction_correct IS NULL
                     AND predicted_at <= ?
                   ORDER BY predicted_at ASC
                   LIMIT ?""",
                (cutoff, limit),
            ) as cur:
                pending = await cur.fetchall()
    except Exception as e:
        logger.error("auto_resolve: failed to fetch pending predictions: %s", e)
        return 0

    if not pending:
        return 0

    logger.info("auto_resolve: found %d predictions to resolve", len(pending))

    # Group by ticker to batch yfinance history downloads
    from collections import defaultdict
    by_ticker: dict = defaultdict(list)
    for pred in pending:
        by_ticker[pred["ticker"]].append(pred)

    resolved = 0
    for ticker, preds in by_ticker.items():
        # Download a wide window covering all predictions for this ticker
        dates = [_parse_timestamp(p["predicted_at"]) for p in preds]
        earliest = min(dates)
        latest   = max(dates)
        fetch_start = earliest.strftime("%Y-%m-%d")
        fetch_end   = (latest + timedelta(days=_HORIZON_DAYS + 5)).strftime("%Y-%m-%d")

        try:
            hist = yf.Ticker(ticker).history(start=fetch_start, end=fetch_end)
        except Exception as e:
            logger.warning("auto_resolve: yfinance download failed for %s: %s", ticker, e)
            continue

        if len(hist) < 2:
            logger.warning("auto_resolve: insufficient history for %s (%d rows)", ticker, len(hist))
            continue

        for pred in preds:
            pred_dt = _parse_timestamp(pred["predicted_at"])
            eval_dt = pred_dt + timedelta(days=_HORIZON_DAYS)

            # Find the closest trading day on or after pred_dt
            entry_rows = hist[hist.index >= pred_dt.strftime("%Y-%m-%d")]
            exit_rows  = hist[hist.index >= eval_dt.strftime("%Y-%m-%d")]

            if entry_rows.empty or exit_rows.empty:
                logger.debug("auto_resolve: no price rows for %s pred %s", ticker, pred["id"])
                continue

            entry_price = float(entry_rows["Close"].iloc[0])
            exit_price  = float(exit_rows["Close"].iloc[0])

            if entry_price <= 0:
                continue

            change_pct    = (exit_price - entry_price) / entry_price * 100
            actual_dir    = _actual_direction(change_pct)
            predicted_dir = pred.get("predicted_direction", "neutral")

            # Normalize legacy "up"/"down" to "bullish"/"bearish" before comparing
            _norm = {"up": "bullish", "down": "bearish"}
            predicted_dir_norm = _norm.get(predicted_dir.lower(), predicted_dir.lower())

            # Neutral predictions abstain — do not mark correct or incorrect
            if predicted_dir_norm == "neutral":
                correct = None   # None = abstain; stored as NULL, excluded from accuracy
            else:
                correct = (predicted_dir_norm == actual_dir)

            try:
                await update_prediction_resolution(
                    prediction_id           = pred["id"],
                    actual_direction        = actual_dir,
                    actual_close_price      = round(exit_price, 4),
                    actual_price_change_pct = round(change_pct, 4),
                    prediction_correct      = correct,   # None for neutral → stored as NULL
                    actual_driver           = "Auto-resolved via 7-day price action",
                    reason_matched          = False,
                    lesson                  = (
                        f"{ticker} moved {change_pct:+.2f}% over 7 days ({actual_dir}). "
                        f"Predicted {predicted_dir_norm}."
                    ),
                    resolved_at             = datetime.now(timezone.utc).isoformat(),
                    resolution_notes        = (
                        f"Entry {entry_price:.3f} → Exit {exit_price:.3f} "
                        f"({change_pct:+.2f}%) over 7 trading days"
                    ),
                )
                resolved += 1
                logger.info(
                    "auto_resolve: [%s] %s predicted=%s actual=%s (%+.2f%%) correct=%s",
                    pred["id"][:16], ticker, predicted_dir, actual_dir, change_pct, correct,
                )
            except Exception as e:
                logger.error("auto_resolve: write-back failed for %s: %s", pred["id"], e)

    logger.info("auto_resolve: resolved %d/%d predictions", resolved, len(pending))
    return resolved
