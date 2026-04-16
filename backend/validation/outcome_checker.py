"""
Automated 24-hour prediction outcome validator for Market Oracle AI.

Validates predictions in prediction_log against actual ASX price movement
24 hours after the signal was generated.

Design notes:
- Complements prediction_resolver.py (7-day horizon) — does NOT replace it.
  The 24h validator gives fast feedback; the 7-day resolver gives the
  authoritative long-horizon outcome.
- "Pending" = prediction_correct IS NULL AND resolved_at IS NULL AND age > 24h.
  Rows already resolved by the 7-day resolver are left untouched.
- Uses bhp_price_at_prediction as the entry price (the column stores the
  relevant ticker's price at signal time, despite its misleading name).
- Outcome is written back via update_prediction_resolution() so it flows
  through to all existing accuracy stats endpoints automatically.
- NEUTRAL predictions (direction='neutral') are skipped — they abstain.

Market hours: 10:00–16:00 AEST/AEDT on ASX trading days (weekdays).
All target times that fall outside market hours are advanced to the next
available market open before price lookup.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_SYDNEY_TZ = ZoneInfo("Australia/Sydney")
_VALIDATION_HORIZON_HOURS = 24       # How long after signal to check price
_MIN_MOVE_PCT = 0.5                  # Threshold to call CORRECT/INCORRECT (%)
_YFINANCE_RETRY_DELAY = 2.0          # Seconds between retries on rate-limit
_YFINANCE_MAX_RETRIES = 3


# ── Timestamp helpers ──────────────────────────────────────────────────────────

def _parse_timestamp(ts_str: str) -> datetime:
    """Parse ISO-8601 string into a timezone-aware UTC datetime."""
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
    except ValueError:
        # Strip trailing timezone fragment and assume UTC
        dt = datetime.fromisoformat(ts_str.split("+")[0].rstrip("Z"))
        return dt.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _next_market_open(dt: datetime) -> datetime:
    """
    Given a datetime, return the next ASX market open (10:00 AEST/AEDT) on or
    after dt. Skips weekends.

    Args:
        dt: Any timezone-aware datetime.
    Returns:
        Timezone-aware datetime of the next (or same-day) market open in Sydney.
    """
    sydney_dt = dt.astimezone(_SYDNEY_TZ)
    open_time = sydney_dt.replace(hour=10, minute=0, second=0, microsecond=0)
    close_time = sydney_dt.replace(hour=16, minute=0, second=0, microsecond=0)

    # If within current trading session, use as-is (caller decides what to do)
    if open_time <= sydney_dt <= close_time and sydney_dt.weekday() < 5:
        return sydney_dt.astimezone(timezone.utc)

    # Advance to next day's open
    candidate = open_time
    if sydney_dt >= close_time or sydney_dt.weekday() >= 5:
        candidate = candidate + timedelta(days=1)

    # Skip weekends (Saturday=5, Sunday=6)
    while candidate.weekday() >= 5:
        candidate = candidate + timedelta(days=1)

    return candidate.replace(hour=10, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _effective_target_time(signal_time: datetime, horizon_hours: int = _VALIDATION_HORIZON_HOURS) -> datetime:
    """
    Return the effective evaluation time: signal_time + horizon, snapped to
    the next available ASX market open if it falls outside trading hours.
    """
    raw_target = signal_time + timedelta(hours=horizon_hours)
    return _next_market_open(raw_target)


# ── yfinance price lookup ──────────────────────────────────────────────────────

async def fetch_price_at_time(ticker: str, target_time: datetime) -> Optional[float]:
    """
    Fetch the ASX closing price on the trading day at or after target_time.

    Handles:
    - Market hour snapping (advances to next open if outside hours)
    - yfinance rate-limit retries (up to _YFINANCE_MAX_RETRIES attempts)
    - Weekend and public-holiday gaps (uses first available row on/after target)

    Returns:
        Close price as float, or None if unavailable (warning is logged).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — cannot fetch price for %s", ticker)
        return None

    effective = _effective_target_time(target_time, horizon_hours=0)
    # Fetch a 7-day window from target to catch the first available trading day
    start_str = effective.strftime("%Y-%m-%d")
    end_date = effective + timedelta(days=7)
    end_str = end_date.strftime("%Y-%m-%d")

    loop = asyncio.get_event_loop()

    for attempt in range(1, _YFINANCE_MAX_RETRIES + 1):
        try:
            hist = await loop.run_in_executor(
                None,
                lambda: yf.Ticker(ticker).history(start=start_str, end=end_str, interval="1d"),
            )
            if hist is None or hist.empty:
                logger.warning(
                    "fetch_price_at_time: no history for %s between %s and %s",
                    ticker, start_str, end_str,
                )
                return None

            # Find the first row on or after the target date
            target_date_str = effective.strftime("%Y-%m-%d")
            rows = hist[hist.index.strftime("%Y-%m-%d") >= target_date_str]
            if rows.empty:
                logger.warning(
                    "fetch_price_at_time: no rows on/after %s for %s",
                    target_date_str, ticker,
                )
                return None

            price = float(rows["Close"].iloc[0])
            return price

        except Exception as exc:
            msg = str(exc).lower()
            if "rate" in msg or "429" in msg or "too many" in msg:
                if attempt < _YFINANCE_MAX_RETRIES:
                    logger.warning(
                        "fetch_price_at_time: rate-limited for %s (attempt %d) — retrying in %.0fs",
                        ticker, attempt, _YFINANCE_RETRY_DELAY,
                    )
                    await asyncio.sleep(_YFINANCE_RETRY_DELAY * attempt)
                    continue
            logger.warning(
                "fetch_price_at_time: failed to fetch %s at %s (attempt %d): %s",
                ticker, start_str, attempt, exc,
            )
            return None

    return None


# ── Core validation logic ──────────────────────────────────────────────────────

def _determine_outcome(
    predicted_direction: str,
    entry_price: float,
    exit_price: float,
) -> tuple[str, float]:
    """
    Compare entry vs exit price against the predicted direction.

    Args:
        predicted_direction: 'bullish', 'bearish', or 'neutral' (case-insensitive)
        entry_price:         Price at signal time
        exit_price:          Price at validation time

    Returns:
        (outcome, change_pct) where outcome is 'CORRECT', 'INCORRECT', or 'NEUTRAL'
    """
    change_pct = (exit_price - entry_price) / entry_price * 100
    direction = predicted_direction.lower()

    # Neutral predictions abstain — never counted as correct or incorrect
    if direction in ("neutral",):
        return "NEUTRAL", change_pct

    moved_up = change_pct > _MIN_MOVE_PCT
    moved_down = change_pct < -_MIN_MOVE_PCT
    moved_significantly = moved_up or moved_down

    if not moved_significantly:
        return "NEUTRAL", change_pct

    # Normalize "up"/"down"/"buy"/"sell" aliases
    is_bullish = direction in ("bullish", "up", "buy")
    is_bearish = direction in ("bearish", "down", "sell")

    if is_bullish and moved_up:
        return "CORRECT", change_pct
    if is_bearish and moved_down:
        return "CORRECT", change_pct
    return "INCORRECT", change_pct


# ── Database helpers ───────────────────────────────────────────────────────────

async def get_pending_validations(limit: int = 200) -> list[dict]:
    """
    Query prediction_log for entries that are ready for 24h validation:
      - prediction_correct IS NULL (not yet resolved)
      - resolved_at IS NULL (not yet resolved by the 7-day resolver either)
      - predicted_at <= now - 24h (old enough to validate)
      - excluded_from_stats = 0 or NULL (skip garbage predictions)
      - predicted_direction != 'neutral' (neutrals abstain)
      - bhp_price_at_prediction IS NOT NULL (need entry price to compare)

    Returns list of row dicts.
    """
    from database import get_db, init_db
    await init_db()

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_VALIDATION_HORIZON_HOURS)).isoformat()

    try:
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT id, ticker, predicted_direction, confidence,
                          predicted_at, bhp_price_at_prediction,
                          primary_reason
                   FROM prediction_log
                   WHERE prediction_correct IS NULL
                     AND resolved_at IS NULL
                     AND predicted_at <= ?
                     AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)
                     AND predicted_direction NOT IN ('neutral')
                     AND bhp_price_at_prediction IS NOT NULL
                     AND bhp_price_at_prediction > 0
                   ORDER BY predicted_at ASC
                   LIMIT ?""",
                (cutoff, limit),
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error("get_pending_validations failed: %s", e)
        return []


async def validate_prediction(prediction: dict) -> str:
    """
    Validate a single prediction row from prediction_log.

    Fetches the actual price at predicted_at + 24h, determines the outcome,
    writes the result back to prediction_log, and returns the outcome string.

    Returns:
        'CORRECT', 'INCORRECT', 'NEUTRAL', or 'SKIPPED' (on price fetch failure)
    """
    from database import update_prediction_resolution

    pred_id = prediction["id"]
    ticker = prediction["ticker"]
    direction = prediction.get("predicted_direction", "neutral")
    entry_price = prediction.get("bhp_price_at_prediction")
    predicted_at_str = prediction.get("predicted_at", "")
    confidence = float(prediction.get("confidence") or 0.0)

    # Parse signal time
    try:
        signal_time = _parse_timestamp(predicted_at_str)
    except Exception as e:
        logger.warning("validate_prediction: cannot parse timestamp for %s: %s", pred_id, e)
        return "SKIPPED"

    # Compute evaluation time and fetch exit price
    target_time = _effective_target_time(signal_time, _VALIDATION_HORIZON_HOURS)
    exit_price = await fetch_price_at_time(ticker, target_time)

    if exit_price is None:
        logger.warning(
            "validate_prediction: SKIPPED %s — could not fetch price for %s at %s",
            pred_id[:16], ticker, target_time.date(),
        )
        return "SKIPPED"

    outcome, change_pct = _determine_outcome(direction, float(entry_price), exit_price)

    # Map outcome string to prediction_correct value expected by the DB function
    correct_flag: Optional[bool]
    if outcome == "CORRECT":
        correct_flag = True
    elif outcome == "INCORRECT":
        correct_flag = False
    else:
        correct_flag = None  # NEUTRAL abstains — stored as NULL

    lesson = (
        f"{ticker} moved {change_pct:+.2f}% over 24h ({outcome.lower()}). "
        f"Predicted {direction} at {confidence:.0%} confidence."
    )
    resolution_notes = (
        f"24h entry {entry_price:.3f} → exit {exit_price:.3f} "
        f"({change_pct:+.2f}%) | threshold {_MIN_MOVE_PCT}%"
    )

    # Log in a human-readable format for Railway/server logs
    logger.info(
        "[VALIDATE] %s %s: %s @ $%.2f → $%.2f (%+.1f%%) = %s",
        ticker,
        signal_time.strftime("%Y-%m-%d"),
        direction.upper(),
        entry_price,
        exit_price,
        change_pct,
        outcome,
    )

    try:
        await update_prediction_resolution(
            prediction_id=pred_id,
            actual_direction="bullish" if change_pct > _MIN_MOVE_PCT else "bearish" if change_pct < -_MIN_MOVE_PCT else "neutral",
            actual_close_price=round(exit_price, 4),
            actual_price_change_pct=round(change_pct, 4),
            prediction_correct=correct_flag,
            actual_driver="Auto-validated via 24h price action",
            reason_matched=False,
            lesson=lesson,
            resolved_at=datetime.now(timezone.utc).isoformat(),
            resolution_notes=resolution_notes,
        )
    except Exception as e:
        logger.error("validate_prediction: write-back failed for %s: %s", pred_id, e)
        return "SKIPPED"

    return outcome


# ── Job runner ─────────────────────────────────────────────────────────────────

async def run_validation_job() -> dict:
    """
    Validate all predictions that are ready for 24h outcome checking.

    Fetches price data ticker-by-ticker (batched to minimise yfinance calls),
    validates each prediction, and returns a summary dict.

    Returns:
        {
            "validated": int,   # predictions successfully validated
            "correct":   int,
            "incorrect": int,
            "neutral":   int,
            "skipped":   int,   # price fetch failed
            "hit_rate":  float, # correct / (correct + incorrect), 0 if none
            "pending_before": int,
        }
    """
    pending = await get_pending_validations()
    pending_count = len(pending)

    if not pending:
        logger.info("run_validation_job: no pending predictions to validate")
        return {
            "validated": 0, "correct": 0, "incorrect": 0,
            "neutral": 0, "skipped": 0, "hit_rate": 0.0,
            "pending_before": 0,
        }

    logger.info("run_validation_job: found %d pending predictions", pending_count)

    counts = {"CORRECT": 0, "INCORRECT": 0, "NEUTRAL": 0, "SKIPPED": 0}

    # Process in small concurrent batches — yfinance handles concurrency poorly
    # so we use a semaphore to cap parallel calls at 3.
    sem = asyncio.Semaphore(3)

    async def _validate_one(pred: dict) -> str:
        async with sem:
            return await validate_prediction(pred)

    results = await asyncio.gather(
        *[_validate_one(p) for p in pending],
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, Exception):
            counts["SKIPPED"] += 1
            logger.error("run_validation_job: unexpected exception: %s", result)
        else:
            counts[result] = counts.get(result, 0) + 1

    validated = counts["CORRECT"] + counts["INCORRECT"] + counts["NEUTRAL"]
    directional = counts["CORRECT"] + counts["INCORRECT"]
    hit_rate = round(counts["CORRECT"] / directional, 3) if directional > 0 else 0.0

    logger.info(
        "run_validation_job: done — validated=%d correct=%d incorrect=%d neutral=%d skipped=%d hit_rate=%.1f%%",
        validated, counts["CORRECT"], counts["INCORRECT"],
        counts["NEUTRAL"], counts["SKIPPED"], hit_rate * 100,
    )

    return {
        "validated": validated,
        "correct": counts["CORRECT"],
        "incorrect": counts["INCORRECT"],
        "neutral": counts["NEUTRAL"],
        "skipped": counts["SKIPPED"],
        "hit_rate": hit_rate,
        "pending_before": pending_count,
    }


# ── Summary statistics ─────────────────────────────────────────────────────────

async def get_validation_summary(days: int = 30) -> dict:
    """
    Return accuracy summary for predictions resolved (by any resolver) in the
    last N days.

    Confidence bands are sized for actionable signals (55%+) matching the
    Market Oracle AI minimum signal threshold.

    Returns a dict matching the spec in the docstring.
    """
    from database import get_db, init_db
    from datetime import timedelta

    await init_db()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Only directional predictions with a resolved outcome and a price entry,
    # resolved within the requested window.
    base_where = """
        WHERE prediction_correct IS NOT NULL
          AND resolved_at >= ?
          AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)
          AND predicted_direction NOT IN ('neutral')
    """

    try:
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

            # Overall totals
            async with db.execute(
                f"SELECT COUNT(*) as total, SUM(prediction_correct) as correct "
                f"FROM prediction_log {base_where}",
                (since,),
            ) as cur:
                overall = await cur.fetchone()

            total_validated = overall["total"] if overall else 0
            correct = int(overall["correct"] or 0) if overall else 0
            incorrect = total_validated - correct
            # Count neutral outcomes separately (they don't appear in prediction_correct)
            async with db.execute(
                f"""SELECT COUNT(*) as n FROM prediction_log
                    WHERE resolved_at >= ?
                      AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)
                      AND actual_direction = 'neutral'
                      AND prediction_correct IS NULL""",
                (since,),
            ) as cur:
                neut_row = await cur.fetchone()
            neutral = neut_row["n"] if neut_row else 0

            # By predicted direction
            async with db.execute(
                f"SELECT predicted_direction, COUNT(*) as total, SUM(prediction_correct) as correct "
                f"FROM prediction_log {base_where} GROUP BY predicted_direction",
                (since,),
            ) as cur:
                dir_rows = await cur.fetchall()

            by_direction: dict = {}
            for row in dir_rows:
                d = row["predicted_direction"]
                t = row["total"]
                c = int(row["correct"] or 0)
                # Normalise display key: bullish→BUY, bearish→SELL
                display = {"bullish": "BUY", "bearish": "SELL"}.get(d, d.upper())
                by_direction[display] = {
                    "total": t,
                    "correct": c,
                    "hit_rate": round(c / t, 3) if t > 0 else 0.0,
                }

            # By confidence band (55%+ bands matching the minimum signal threshold)
            confidence_bands = [
                ("55-65%", 0.55, 0.65),
                ("65-75%", 0.65, 0.75),
                ("75-85%", 0.75, 0.85),
                ("85%+",   0.85, 1.01),
            ]
            by_confidence_band: dict = {}
            for label, lo, hi in confidence_bands:
                async with db.execute(
                    f"SELECT COUNT(*) as total, SUM(prediction_correct) as correct "
                    f"FROM prediction_log {base_where} AND confidence >= ? AND confidence < ?",
                    (since, lo, hi),
                ) as cur:
                    band_row = await cur.fetchone()
                t = band_row["total"] if band_row else 0
                c = int(band_row["correct"] or 0) if band_row else 0
                by_confidence_band[label] = {
                    "total": t,
                    "hit_rate": round(c / t, 3) if t > 0 else 0.0,
                }

        directional = correct + incorrect
        hit_rate = round(correct / directional, 3) if directional > 0 else 0.0
        # Excluding neutral: same as hit_rate when neutrals aren't in the denominator
        # (they're tracked separately, not in prediction_correct)
        hit_rate_excl_neutral = hit_rate

        return {
            "period_days": days,
            "total_validated": total_validated,
            "correct": correct,
            "incorrect": incorrect,
            "neutral": neutral,
            "hit_rate": hit_rate,
            "hit_rate_excluding_neutral": hit_rate_excl_neutral,
            "by_direction": by_direction,
            "by_confidence_band": by_confidence_band,
        }

    except Exception as e:
        logger.error("get_validation_summary failed: %s", e)
        return {
            "period_days": days,
            "total_validated": 0,
            "correct": 0, "incorrect": 0, "neutral": 0,
            "hit_rate": 0.0, "hit_rate_excluding_neutral": 0.0,
            "by_direction": {}, "by_confidence_band": {},
            "error": str(e),
        }
