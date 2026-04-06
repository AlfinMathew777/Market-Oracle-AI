"""Risk metrics — Historical VaR, CVaR (Expected Shortfall), Sharpe, max drawdown.

All metrics are computed from the price series passed at construction.
Uses only numpy/pandas (already in requirements.txt).
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252
_RBA_CASH_RATE = 0.035  # ~3.5% — update if RBA changes (approx Mar 2026)


class RiskMetrics:
    """Computes portfolio risk metrics from a daily closing price series."""

    def __init__(self, prices) -> None:
        self._prices = prices
        self._returns = prices.pct_change().dropna()

    def var(self, confidence: float = 0.95, window: int = 252) -> float:
        """Historical VaR at *confidence* level (1-day, returned as positive fraction).

        e.g. 0.045 means 4.5% potential 1-day loss at 95% confidence.
        """
        try:
            recent = self._returns.tail(window)
            loss_pct = (1.0 - confidence) * 100.0
            return float(abs(np.percentile(recent.values, loss_pct)))
        except Exception as e:
            logger.warning("VaR failed: %s", e)
            return 0.03

    def cvar(self, confidence: float = 0.95, window: int = 252) -> float:
        """Conditional VaR / Expected Shortfall — average loss beyond VaR threshold.

        Returns positive fraction (e.g. 0.062 = 6.2% average tail loss).
        """
        try:
            recent = self._returns.tail(window)
            threshold = np.percentile(recent.values, (1.0 - confidence) * 100.0)
            tail_losses = recent[recent <= threshold]
            if len(tail_losses) == 0:
                return self.var(confidence, window) * 1.3
            return float(abs(tail_losses.mean()))
        except Exception as e:
            logger.warning("CVaR failed: %s", e)
            return 0.04

    def sharpe(self, risk_free: float = _RBA_CASH_RATE) -> float:
        """Annualised Sharpe ratio using the RBA cash rate as risk-free benchmark."""
        try:
            annual_ret = float(self._returns.mean() * _TRADING_DAYS)
            annual_std = float(self._returns.std() * np.sqrt(_TRADING_DAYS))
            if annual_std <= 0:
                return 0.0
            return round((annual_ret - risk_free) / annual_std, 3)
        except Exception as e:
            logger.warning("Sharpe failed: %s", e)
            return 0.0

    def max_drawdown(self) -> float:
        """Maximum peak-to-trough drawdown over the full price series (positive fraction)."""
        try:
            rolling_max = self._prices.cummax()
            drawdown = (self._prices - rolling_max) / rolling_max
            return round(float(abs(drawdown.min())), 4)
        except Exception as e:
            logger.warning("MaxDD failed: %s", e)
            return 0.0
