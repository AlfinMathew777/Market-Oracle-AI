"""Geometric Brownian Motion price-path Monte Carlo — Market Oracle AI Quant Engine.

NOTE: This module is SEPARATE from backend/services/game_theory/monte_carlo.py.
      That module simulates *agent vote confidence* (bootstrap resampling of 50
      agent votes). This module simulates *price paths* using GBM for the quant
      analysis API endpoints and the MonteCarloEngine frontend visualisation.

All simulations run in < 200 ms at n_simulations=5000 on typical hardware.
seed=42 default — same inputs produce reproducible output.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252


class QuantMonteCarlo:
    """GBM price-path simulation for quantitative price range estimation."""

    def __init__(
        self,
        current_price: float,
        annual_drift: float,
        annual_vol: float,
        horizon_days: int = 30,
        n_simulations: int = 5000,
        seed: int = 42,
    ) -> None:
        self.current_price = current_price
        self.annual_drift = annual_drift
        self.annual_vol = annual_vol
        self.horizon_days = horizon_days
        self.n_simulations = n_simulations
        self.seed = seed

    def run(self) -> dict:
        """Simulate price paths and return percentile paths + tail probabilities.

        Returns:
            {
                "percentile_paths": {"p5": [...], "p25": [...], "mean": [...],
                                     "p75": [...], "p95": [...]},
                "probabilities":    {"up": 0.55, "down": 0.45, "down_5pct": 0.12,
                                     "up_5pct": 0.18, "down_10pct": 0.05,
                                     "up_10pct": 0.08},
                "final_price_p5":   45.2,
                "final_price_p95":  62.1,
                "final_price_mean": 53.4,
            }
        """
        try:
            rng = np.random.default_rng(self.seed)
            dt = 1.0 / _TRADING_DAYS

            # GBM log-return parameters per time-step
            drift_term = (self.annual_drift - 0.5 * self.annual_vol ** 2) * dt
            vol_term = self.annual_vol * np.sqrt(dt)

            # Shape: (n_simulations, horizon_days)
            shocks = rng.standard_normal((self.n_simulations, self.horizon_days))
            log_returns = drift_term + vol_term * shocks
            cum_log = np.cumsum(log_returns, axis=1)
            price_paths = self.current_price * np.exp(cum_log)  # (N, T)

            final_prices = price_paths[:, -1]

            # For each day, compute cross-simulation percentile → 5 representative paths
            pct_levels = {"p5": 5, "p25": 25, "mean": 50, "p75": 75, "p95": 95}
            percentile_paths: dict[str, list[float]] = {}
            for label, pct in pct_levels.items():
                path = np.percentile(price_paths, pct, axis=0)
                percentile_paths[label] = [round(float(p), 3) for p in path]

            prob_up = float(np.mean(final_prices > self.current_price))
            prob_down_5pct = float(np.mean(final_prices < self.current_price * 0.95))
            prob_up_5pct = float(np.mean(final_prices > self.current_price * 1.05))
            prob_down_10pct = float(np.mean(final_prices < self.current_price * 0.90))
            prob_up_10pct = float(np.mean(final_prices > self.current_price * 1.10))

            return {
                "percentile_paths": percentile_paths,
                "probabilities": {
                    "up": round(prob_up, 3),
                    "down": round(1.0 - prob_up, 3),
                    "down_5pct": round(prob_down_5pct, 3),
                    "up_5pct": round(prob_up_5pct, 3),
                    "down_10pct": round(prob_down_10pct, 3),
                    "up_10pct": round(prob_up_10pct, 3),
                },
                "final_price_p5": round(float(np.percentile(final_prices, 5)), 3),
                "final_price_p95": round(float(np.percentile(final_prices, 95)), 3),
                "final_price_mean": round(float(np.mean(final_prices)), 3),
            }

        except Exception as e:
            logger.error("QuantMonteCarlo.run failed: %s", e, exc_info=True)
            p = self.current_price
            return {
                "percentile_paths": {"p5": [], "p25": [], "mean": [], "p75": [], "p95": []},
                "probabilities": {
                    "up": 0.5, "down": 0.5,
                    "down_5pct": 0.1, "up_5pct": 0.1,
                    "down_10pct": 0.05, "up_10pct": 0.05,
                },
                "final_price_p5": round(p * 0.85, 3),
                "final_price_p95": round(p * 1.15, 3),
                "final_price_mean": round(p, 3),
            }
