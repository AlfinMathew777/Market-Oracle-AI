"""
Volatility Calibration for Monte Carlo — Market Oracle AI
-----------------------------------------------------------
Wraps VolatilityModel (quant_engine) with timeframe-aware blending.
Used by run_price_range_monte_carlo() to replace hardcoded DAILY_VOL table.
"""

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252

# Lookback window and EWMA decay per prediction horizon.
_TIMEFRAME_CONFIG: dict[str, dict[str, Any]] = {
    "1_day":  {"lookback_days": 10, "vol_adjustment": 1.30, "ewma_weight": 0.80},
    "7_day":  {"lookback_days": 20, "vol_adjustment": 1.15, "ewma_weight": 0.70},
    "14_day": {"lookback_days": 30, "vol_adjustment": 1.10, "ewma_weight": 0.60},
    "30_day": {"lookback_days": 60, "vol_adjustment": 1.05, "ewma_weight": 0.50},
    "90_day": {"lookback_days": 120, "vol_adjustment": 1.00, "ewma_weight": 0.50},
}

# Fallback hardcoded daily vols when no price series is available.
_FALLBACK_DAILY_VOL: dict[str, float] = {
    "BHP.AX": 0.011,
    "CBA.AX": 0.007,
    "RIO.AX": 0.012,
    "FMG.AX": 0.015,
    "WDS.AX": 0.009,
    "STO.AX": 0.010,
}
_DEFAULT_FALLBACK_DAILY_VOL = 0.011


def calibrate_daily_vol(price_series, timeframe: str = "7_day") -> tuple[float, str]:
    """
    Return (daily_volatility, regime) calibrated for the given timeframe.

    Uses the existing VolatilityModel from the quant engine.  Falls back
    to the hardcoded table if the price series is None or too short.

    Args:
        price_series: pandas Series of daily close prices (at least 21 rows).
        timeframe:    One of "1_day", "7_day", "14_day", "30_day", "90_day".

    Returns:
        (daily_vol, regime) — daily_vol ready to pass straight into GBM.
    """
    try:
        from quant_engine.volatility_model import VolatilityModel

        cfg = _TIMEFRAME_CONFIG.get(timeframe, _TIMEFRAME_CONFIG["7_day"])
        lookback = cfg["lookback_days"]
        ewma_w = cfg["ewma_weight"]
        adj = cfg["vol_adjustment"]

        if price_series is None or len(price_series) < lookback + 1:
            raise ValueError(
                f"price_series has {len(price_series) if price_series is not None else 0} rows, "
                f"need ≥ {lookback + 1}"
            )

        recent = price_series.tail(lookback + 1)
        vm = VolatilityModel(recent)

        realized_annual = vm.annual_volatility(window=lookback)
        ewma_annual = vm.ewma_volatility()
        regime = vm.regime()

        # Blend: weight EWMA more heavily for short horizons (captures clustering).
        blended_annual = ewma_w * ewma_annual + (1.0 - ewma_w) * realized_annual

        # Regime bump: widen in extremes, slight bump in calm to avoid overconfidence.
        regime_mult = 1.0
        if regime == "EXTREME":
            regime_mult = 1.20
        elif regime == "LOW":
            regime_mult = 1.10

        adjusted_annual = blended_annual * adj * regime_mult

        daily_vol = adjusted_annual / np.sqrt(_TRADING_DAYS)

        logger.info(
            "[VOL CAL] %s horizon | realized=%.3f ewma=%.3f blended=%.3f "
            "adj=%.3f regime=%s → daily_vol=%.5f",
            timeframe, realized_annual, ewma_annual, blended_annual,
            adjusted_annual, regime, daily_vol,
        )
        return daily_vol, regime

    except Exception as exc:
        logger.warning("[VOL CAL] Calibration failed (%s) — using fallback", exc)
        return _DEFAULT_FALLBACK_DAILY_VOL, "UNKNOWN"


def fallback_daily_vol(ticker: str) -> float:
    """Return the hardcoded fallback daily vol for a ticker."""
    return _FALLBACK_DAILY_VOL.get(ticker, _DEFAULT_FALLBACK_DAILY_VOL)
