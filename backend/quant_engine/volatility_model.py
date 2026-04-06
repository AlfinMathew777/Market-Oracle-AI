"""Volatility modeling — historical vol, EWMA, and regime classification.

All methods are pure functions of the price series passed at construction.
No global state, no side effects.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252


class VolatilityModel:
    """Computes volatility metrics from a pandas price series."""

    def __init__(self, prices) -> None:
        self._prices = prices
        self._returns = prices.pct_change().dropna()

    def annual_volatility(self, window: int = 30) -> float:
        """Rolling *window*-day historical volatility, annualised."""
        try:
            recent = self._returns.tail(window)
            return float(recent.std() * np.sqrt(_TRADING_DAYS))
        except Exception as e:
            logger.warning("HV calc failed: %s", e)
            return 0.25

    def annual_drift(self) -> float:
        """Annualised mean log-return (GBM drift parameter mu)."""
        try:
            log_rets = np.log(self._prices / self._prices.shift(1)).dropna()
            return float(log_rets.mean() * _TRADING_DAYS)
        except Exception as e:
            logger.warning("Drift calc failed: %s", e)
            return 0.0

    def ewma_volatility(self, lam: float = 0.94) -> float:
        """EWMA (RiskMetrics λ=0.94) volatility estimate, annualised."""
        try:
            sq = self._returns ** 2
            ewma_var = sq.ewm(com=(1 - lam) / lam).mean().iloc[-1]
            return float(np.sqrt(ewma_var * _TRADING_DAYS))
        except Exception as e:
            logger.warning("EWMA vol failed: %s", e)
            return self.annual_volatility()

    def regime(self) -> str:
        """Classify annualised volatility into a regime label.

        LOW      < 15 %
        NORMAL   15–25 %
        HIGH     25–40 %
        EXTREME  > 40 %
        """
        vol = self.annual_volatility()
        if vol < 0.15:
            return "LOW"
        if vol < 0.25:
            return "NORMAL"
        if vol < 0.40:
            return "HIGH"
        return "EXTREME"
