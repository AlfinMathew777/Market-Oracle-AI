"""Loader-boundary data guards for backtesting.

The value of the platform is its track record, and the track record is only as
clean as the bars it was computed from. These guards sit at the data boundary
so every downstream consumer (signal generation, outcome labelling, metrics)
works from validated bars:

  - OHLC sanity: structurally impossible bars (high < low, non-positive
    prices, high/low failing to bracket open/close) are dropped before they
    can surface as NaN/inf metrics or phantom outcomes.
  - Bounded exit gap: an outcome labelled "next trading day" must actually be
    near the prediction day. A halt or long data gap otherwise turns a 3-week
    move into a "next-day" outcome and silently corrupts the hit rate.

Pattern adapted from HKUDS/Vibe-Trading (MIT) backtest loader guards.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Maximum calendar days between prediction day and the exit bar for an outcome
# to still count as a next-day outcome. Covers weekends + one public holiday;
# anything longer is a halt or data gap and the prediction is unvalidatable.
MAX_EXIT_GAP_DAYS = 5


def validate_ohlc(
    frame: pd.DataFrame,
    *,
    strategy: str = "drop",
    label: str = "",
) -> pd.DataFrame:
    """Drop, flag, or reject bars that violate OHLC invariants.

    Structural invariants: high >= low, and high/low must bracket open/close.
    Positivity: ASX equities never trade at or below zero, so any non-positive
    price is a corrupt bar.

    Args:
        frame: OHLCV frame with open/high/low/close columns (any casing).
               NaN handling is left to the caller's dropna.
        strategy: "drop" (remove offending rows, default), "warn" (log and
                  keep), or "raise" (raise on any violation).
        label: context string for log messages (e.g. the ticker).

    Returns:
        The frame with invalid rows removed ("drop") or unchanged ("warn").
        A frame that is empty or lacks OHLC columns is returned as-is.

    Raises:
        ValueError: strategy="raise" and at least one bar is invalid.
    """
    columns = _resolve_ohlc_columns(frame)
    if frame.empty or columns is None:
        return frame

    open_, high, low, close = (frame[columns[k]] for k in ("open", "high", "low", "close"))
    structural = (
        (high < low)
        | (high < open_)
        | (high < close)
        | (low > open_)
        | (low > close)
    )
    nonpositive = (open_ <= 0) | (high <= 0) | (low <= 0) | (close <= 0)
    invalid = structural | nonpositive
    n_invalid = int(invalid.sum())
    if n_invalid == 0:
        return frame

    context = f" for {label}" if label else ""
    if strategy == "raise":
        raise ValueError(f"{n_invalid} bar(s){context} violate OHLC invariants")
    if strategy == "warn":
        logger.warning("OHLC validation%s: %d bar(s) violate invariants (kept)", context, n_invalid)
        return frame
    logger.warning("OHLC validation%s: dropping %d invalid bar(s)", context, n_invalid)
    return frame[~invalid]


def _resolve_ohlc_columns(frame: pd.DataFrame) -> dict[str, str] | None:
    """Map canonical ohlc names to the frame's actual column names (any casing)."""
    lookup = {str(col).lower(): col for col in frame.columns}
    required = ("open", "high", "low", "close")
    if not all(name in lookup for name in required):
        return None
    return {name: lookup[name] for name in required}


def exit_gap_ok(
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    max_gap_days: int = MAX_EXIT_GAP_DAYS,
) -> bool:
    """Return whether an exit bar is close enough to count as next-day.

    Args:
        entry_ts: prediction-day timestamp.
        exit_ts:  timestamp of the first available bar after entry.
        max_gap_days: maximum allowed calendar-day gap.

    Returns:
        True when the gap is within bounds; False for halts / data gaps.
    """
    gap_days = (exit_ts - entry_ts).days
    return 0 < gap_days <= max_gap_days


def sane_close_price(price: float | None, *, label: str = "") -> float | None:
    """Reject non-positive or non-finite close prices at the fetch boundary.

    Returns the price unchanged when sane, None otherwise (with a warning).
    """
    if price is None:
        return None
    try:
        value = float(price)
    except (TypeError, ValueError):
        logger.warning("close price sanity%s: non-numeric price %r rejected",
                       f" for {label}" if label else "", price)
        return None
    if not pd.notna(value) or value <= 0 or value == float("inf"):
        logger.warning("close price sanity%s: invalid price %r rejected",
                       f" for {label}" if label else "", price)
        return None
    return value
