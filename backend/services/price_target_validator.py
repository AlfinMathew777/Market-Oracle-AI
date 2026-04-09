"""Price target validator for Market Oracle AI.

Caps unrealistic 7-day price targets at statistically defensible bounds
derived from the ticker's own historical volatility (ATR-based).

A target is considered unrealistic when:
  |target - current| > ATR(14) × sqrt(days) × 2.5

The multiplier 2.5 corresponds roughly to the 99th percentile of a
normally-distributed price move, so only genuine outlier targets are capped.
"""

import logging
import math
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Fallback daily volatility (fraction) by asset class when ATR unavailable.
# Calibrated from 2023-2025 historical data for ASX large-caps.
_FALLBACK_DAILY_VOL: dict[str, float] = {
    "BHP.AX":  0.017,
    "RIO.AX":  0.018,
    "FMG.AX":  0.025,
    "WDS.AX":  0.018,
    "STO.AX":  0.020,
    "CBA.AX":  0.012,
    "NAB.AX":  0.012,
    "ANZ.AX":  0.013,
    "WBC.AX":  0.013,
    "CSL.AX":  0.014,
}
_DEFAULT_DAILY_VOL = 0.020  # 2% daily vol for unknown tickers


def _calculate_atr(price_series: pd.Series, period: int = 14) -> Optional[float]:
    """Calculate ATR(14) from a closing-price series.

    Returns None if the series is too short or contains errors.
    """
    try:
        if len(price_series) < period + 2:
            return None
        high = price_series
        low  = price_series
        # Approximation: use daily-range proxy from close series only.
        # Full ATR (H/L/C) requires OHLC data; this returns a simplified ATR
        # that is still directionally correct for target validation.
        daily_range = price_series.rolling(2).apply(lambda x: abs(x.iloc[1] - x.iloc[0]))
        atr = daily_range.rolling(period).mean().iloc[-1]
        return float(atr) if not math.isnan(atr) else None
    except Exception as e:
        logger.warning("ATR calculation failed: %s", e)
        return None


def _fetch_atr_from_yfinance(ticker: str, period: int = 14) -> Optional[float]:
    """Fetch proper True Range ATR(14) from yfinance OHLCV data."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="3mo")
        if hist.empty or len(hist) < period + 2:
            return None
        high  = hist["High"]
        low   = hist["Low"]
        close = hist["Close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not math.isnan(atr) else None
    except Exception as e:
        logger.warning("[PRICE TARGET] yfinance ATR fetch failed for %s: %s", ticker, e)
        return None


def _max_realistic_move(current_price: float, atr: float, days: int) -> float:
    """Maximum realistic absolute price move over `days` days.

    Formula: ATR × sqrt(days) × 2.5  (≈ 99th-pct normally-distributed move)
    """
    return atr * math.sqrt(days) * 2.5


def validate_price_target(
    ticker: str,
    current_price: float,
    target_price: float,
    days: int = 7,
    price_series: Optional[pd.Series] = None,
    atr_override: Optional[float] = None,
) -> dict:
    """Check whether a price target is statistically realistic.

    Returns a dict with:
        original_target        — the input target
        adjusted_target        — capped target (= original if realistic)
        is_realistic           — True when no cap was needed
        actual_move_pct        — % move implied by the original target
        max_realistic_move_pct — % move cap based on ATR
        atr_14                 — ATR value used
        days                   — look-ahead horizon
        warning                — human-readable explanation if target was capped

    Args:
        ticker:         ASX ticker (used for fallback vol lookup).
        current_price:  Stock price at time of prediction.
        target_price:   Predicted target price.
        days:           Look-ahead days (default 7).
        price_series:   Optional pandas Series of recent closes for ATR estimation.
        atr_override:   If provided, skip yfinance fetch and use this ATR directly.
    """
    if current_price <= 0:
        return {
            "original_target": target_price,
            "adjusted_target": target_price,
            "is_realistic": True,
            "actual_move_pct": 0.0,
            "max_realistic_move_pct": 0.0,
            "atr_14": None,
            "days": days,
            "warning": None,
        }

    # 1. Determine ATR — try override → price_series → yfinance → fallback vol
    atr: Optional[float] = atr_override
    if atr is None and price_series is not None:
        atr = _calculate_atr(price_series)
    if atr is None:
        atr = _fetch_atr_from_yfinance(ticker)
    if atr is None:
        daily_vol = _FALLBACK_DAILY_VOL.get(ticker, _DEFAULT_DAILY_VOL)
        atr = current_price * daily_vol
        logger.info("[PRICE TARGET] Using fallback vol %.2f%% for %s", daily_vol * 100, ticker)

    max_move    = _max_realistic_move(current_price, atr, days)
    actual_move = abs(target_price - current_price)

    actual_move_pct     = round(actual_move / current_price * 100, 2)
    max_realistic_pct   = round(max_move / current_price * 100, 2)
    is_realistic        = actual_move <= max_move

    if is_realistic:
        adjusted_target = target_price
        warning = None
    else:
        # Cap at max realistic move in the same direction
        if target_price >= current_price:
            adjusted_target = round(current_price + max_move, 4)
        else:
            adjusted_target = round(current_price - max_move, 4)
        warning = (
            f"Target capped: implied move {actual_move_pct:.1f}% exceeds "
            f"ATR-based maximum {max_realistic_pct:.1f}% over {days} days"
        )
        logger.info("[PRICE TARGET] %s target capped %.4f → %.4f (%s)",
                    ticker, target_price, adjusted_target, warning)

    return {
        "original_target":        round(target_price, 4),
        "adjusted_target":        round(adjusted_target, 4),
        "is_realistic":           is_realistic,
        "actual_move_pct":        actual_move_pct,
        "max_realistic_move_pct": max_realistic_pct,
        "atr_14":                 round(atr, 4),
        "days":                   days,
        "warning":                warning,
    }
