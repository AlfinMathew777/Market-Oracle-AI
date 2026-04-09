"""
CVaR (Conditional Value-at-Risk) Optimizer
-------------------------------------------
Implements tail-risk metrics adapted from NVIDIA quantitative portfolio optimization.
CPU-only implementation using NumPy.

References:
- Rockafellar & Uryasev (2000): "Optimization of conditional value-at-risk"
- NVIDIA AI Blueprints: quantitative-portfolio-optimization
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """Container for CVaR risk analysis results."""

    # Core risk metrics
    var_95: float            # Value-at-Risk at 95% confidence
    cvar_95: float           # Conditional VaR (Expected Shortfall) at 95%
    var_99: float            # VaR at 99% confidence (extreme tail)
    cvar_99: float           # CVaR at 99% confidence

    # Return distribution
    expected_return: float   # Mean return across scenarios
    median_return: float     # Median return
    best_case: float         # Best scenario return
    worst_case: float        # Worst scenario return
    return_std: float        # Standard deviation of returns

    # Probability metrics
    prob_profit: float       # P(return > 0)
    prob_loss_5pct: float    # P(return < -5%)
    prob_loss_10pct: float   # P(return < -10%)
    prob_gain_5pct: float    # P(return > +5%)
    prob_gain_10pct: float   # P(return > +10%)

    # Risk-adjusted metrics
    risk_adjusted_score: float   # Sharpe-like ratio (return / |CVaR|)
    tail_risk_ratio: float       # CVaR / VaR — measures tail heaviness

    # Price projections
    current_price: float
    mean_price: float
    median_price: float
    price_5th_pct: float         # 5th percentile price
    price_95th_pct: float        # 95th percentile price

    # Simulation metadata
    n_scenarios: int
    n_days: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "var_95": round(self.var_95, 2),
            "cvar_95": round(self.cvar_95, 2),
            "var_99": round(self.var_99, 2),
            "cvar_99": round(self.cvar_99, 2),
            "expected_return": round(self.expected_return, 2),
            "median_return": round(self.median_return, 2),
            "best_case": round(self.best_case, 2),
            "worst_case": round(self.worst_case, 2),
            "return_std": round(self.return_std, 2),
            "prob_profit": round(self.prob_profit, 1),
            "prob_loss_5pct": round(self.prob_loss_5pct, 1),
            "prob_loss_10pct": round(self.prob_loss_10pct, 1),
            "prob_gain_5pct": round(self.prob_gain_5pct, 1),
            "prob_gain_10pct": round(self.prob_gain_10pct, 1),
            "risk_adjusted_score": round(self.risk_adjusted_score, 3),
            "tail_risk_ratio": round(self.tail_risk_ratio, 2),
            "current_price": round(self.current_price, 2),
            "mean_price": round(self.mean_price, 2),
            "median_price": round(self.median_price, 2),
            "price_5th_pct": round(self.price_5th_pct, 2),
            "price_95th_pct": round(self.price_95th_pct, 2),
            "n_scenarios": self.n_scenarios,
            "n_days": self.n_days,
            "var_95_interpretation": f"95% confident loss won't exceed {abs(round(self.var_95, 1))}%",
            "cvar_95_interpretation": f"In worst 5% of scenarios, avg loss is {abs(round(self.cvar_95, 1))}%",
            "risk_level": self._get_risk_level(),
        }

    def _get_risk_level(self) -> str:
        """Classify overall risk level based on CVaR magnitude."""
        cvar = abs(self.cvar_95)
        if cvar < 3:
            return "LOW"
        elif cvar < 7:
            return "MEDIUM"
        elif cvar < 12:
            return "HIGH"
        return "VERY HIGH"


class CVaROptimizer:
    """
    Calculates Conditional Value-at-Risk (CVaR) and related risk metrics.

    CVaR (also called Expected Shortfall) answers:
    "In the worst X% of scenarios, what's the average loss?"

    This is more informative than VaR because it considers the
    magnitude of losses in the tail, not just the threshold.

    Example:
        VaR 95% = -5%  → "95% sure you won't lose more than 5%"
        CVaR 95% = -8% → "In worst 5% of cases, avg loss is 8%"
    """

    def __init__(self, n_scenarios: int = 10000, seed: Optional[int] = None) -> None:
        self.n_scenarios = n_scenarios
        self.rng = np.random.default_rng(seed)

    def calculate_var(self, returns: np.ndarray, confidence: float = 0.95) -> float:
        """
        Value-at-Risk at given confidence level.

        Args:
            returns: Array of simulated returns (as fractions, e.g. -0.05 = -5%)
            confidence: Confidence level (0.95 = 95%)

        Returns:
            VaR as a percentage (negative for losses)
        """
        alpha = 1 - confidence
        return float(np.percentile(returns, alpha * 100)) * 100

    def calculate_cvar(self, returns: np.ndarray, confidence: float = 0.95) -> float:
        """
        Conditional Value-at-Risk (Expected Shortfall).

        Args:
            returns: Array of simulated returns (as fractions)
            confidence: Confidence level (0.95 = 95%)

        Returns:
            CVaR as a percentage (negative for losses)
        """
        alpha = 1 - confidence
        var_threshold = np.percentile(returns, alpha * 100)
        tail_returns = returns[returns <= var_threshold]
        if len(tail_returns) == 0:
            return float(var_threshold) * 100
        return float(np.mean(tail_returns)) * 100

    def calculate_from_returns(
        self,
        returns: np.ndarray,
        current_price: float,
        n_days: int,
    ) -> RiskMetrics:
        """
        Compute all risk metrics from a pre-simulated returns array.

        Args:
            returns: 1-D array of cumulative fractional returns (e.g. 0.05 = +5%)
            current_price: Current stock price for price projections
            n_days: Simulation horizon in days (metadata only)

        Returns:
            RiskMetrics dataclass
        """
        final_prices = current_price * (1 + returns)
        n = len(returns)

        var_95 = self.calculate_var(returns, 0.95)
        cvar_95 = self.calculate_cvar(returns, 0.95)
        var_99 = self.calculate_var(returns, 0.99)
        cvar_99 = self.calculate_cvar(returns, 0.99)

        expected_return = float(np.mean(returns)) * 100
        prob_profit = float(np.mean(returns > 0)) * 100

        risk_adjusted_score = (
            expected_return / abs(cvar_95) if abs(cvar_95) > 0.01 else 0.0
        )
        tail_risk_ratio = (
            abs(cvar_95) / abs(var_95) if abs(var_95) > 0.01 else 1.0
        )

        return RiskMetrics(
            var_95=var_95,
            cvar_95=cvar_95,
            var_99=var_99,
            cvar_99=cvar_99,
            expected_return=expected_return,
            median_return=float(np.median(returns)) * 100,
            best_case=float(np.max(returns)) * 100,
            worst_case=float(np.min(returns)) * 100,
            return_std=float(np.std(returns)) * 100,
            prob_profit=prob_profit,
            prob_loss_5pct=float(np.mean(returns < -0.05)) * 100,
            prob_loss_10pct=float(np.mean(returns < -0.10)) * 100,
            prob_gain_5pct=float(np.mean(returns > 0.05)) * 100,
            prob_gain_10pct=float(np.mean(returns > 0.10)) * 100,
            risk_adjusted_score=risk_adjusted_score,
            tail_risk_ratio=tail_risk_ratio,
            current_price=current_price,
            mean_price=float(np.mean(final_prices)),
            median_price=float(np.median(final_prices)),
            price_5th_pct=float(np.percentile(final_prices, 5)),
            price_95th_pct=float(np.percentile(final_prices, 95)),
            n_scenarios=n,
            n_days=n_days,
        )

    def simulate_and_calculate(
        self,
        current_price: float,
        daily_volatility: float,
        n_days: int = 7,
        drift: float = 0.0,
        n_scenarios: Optional[int] = None,
    ) -> RiskMetrics:
        """
        Run Monte Carlo simulation and compute CVaR metrics in one step.

        Args:
            current_price: Current stock price
            daily_volatility: Daily volatility (not annualized)
            n_days: Prediction horizon in days
            drift: Expected daily return adjustment
            n_scenarios: Number of scenarios (uses default if None)
        """
        n = n_scenarios or self.n_scenarios
        random_shocks = self.rng.standard_normal((n, n_days))
        daily_returns = np.exp(
            (drift - 0.5 * daily_volatility**2) + daily_volatility * random_shocks
        )
        cumulative_returns = np.prod(daily_returns, axis=1) - 1
        return self.calculate_from_returns(cumulative_returns, current_price, n_days)

    def get_risk_interpretation(self, metrics: RiskMetrics) -> Dict[str, str]:
        """Generate human-readable risk interpretations."""
        interps: Dict[str, str] = {}

        interps["var_95"] = (
            f"95% confident the {metrics.n_days}-day loss won't exceed "
            f"{abs(metrics.var_95):.1f}%"
        )
        interps["cvar_95"] = (
            f"In the worst 5% of scenarios, expect to lose "
            f"{abs(metrics.cvar_95):.1f}% on average"
        )

        if metrics.prob_profit >= 60:
            interps["outlook"] = f"Favorable: {metrics.prob_profit:.0f}% chance of profit"
        elif metrics.prob_profit >= 45:
            interps["outlook"] = f"Neutral: {metrics.prob_profit:.0f}% chance of profit"
        else:
            interps["outlook"] = f"Unfavorable: only {metrics.prob_profit:.0f}% chance of profit"

        if metrics.tail_risk_ratio > 1.5:
            interps["tail_risk"] = "Heavy tail risk detected — extreme losses possible"
        elif metrics.tail_risk_ratio > 1.2:
            interps["tail_risk"] = "Moderate tail risk — some skew toward losses"
        else:
            interps["tail_risk"] = "Normal tail risk — returns roughly symmetric"

        interps["risk_level"] = metrics._get_risk_level()
        return interps


def calculate_cvar_metrics(
    current_price: float,
    daily_volatility: float,
    n_days: int = 7,
    drift: float = 0.0,
    n_scenarios: int = 10000,
) -> Dict[str, Any]:
    """
    Convenience function: run CVaR analysis and return JSON-ready dict.

    Args:
        current_price: Current stock price
        daily_volatility: Daily volatility (not annualized)
        n_days: Prediction horizon
        drift: Expected daily return adjustment
        n_scenarios: Number of Monte Carlo scenarios

    Returns:
        Dictionary of risk metrics ready for JSON response
    """
    optimizer = CVaROptimizer(n_scenarios=n_scenarios)
    metrics = optimizer.simulate_and_calculate(
        current_price=current_price,
        daily_volatility=daily_volatility,
        n_days=n_days,
        drift=drift,
    )
    result = metrics.to_dict()
    result["interpretations"] = optimizer.get_risk_interpretation(metrics)
    return result
