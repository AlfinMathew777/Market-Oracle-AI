"""QuantEngine — main orchestrator for the Market Oracle AI quant analysis package.

Orchestrates: VolatilityModel → FactorModel → QuantMonteCarlo →
              TechnicalAnalysis → RiskMetrics into a single unified result dict.

All failures are caught and returned as {"status": "error", ...} so that
the existing agent pipeline is NEVER interrupted by quant engine failures.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class QuantEngine:
    """Run full quantitative analysis for an ASX ticker."""

    def __init__(
        self,
        ticker: str,
        horizon_days: int = 30,
        n_simulations: int = 5000,
    ) -> None:
        self.ticker = ticker
        self.horizon_days = max(5, min(horizon_days, 90))
        self.n_simulations = max(1000, min(n_simulations, 10000))

    # ── Public interface ─────────────────────────────────────────────────────

    def analyse(self) -> dict:
        """Full quantitative analysis.

        Returns a dict matching the /api/quant/monte-carlo response shape so
        the same result can serve both the analyse and monte-carlo endpoints.
        """
        try:
            from .volatility_model import VolatilityModel
            from .factor_model import FactorModel
            from .monte_carlo import QuantMonteCarlo
            from .technical_analysis import TechnicalAnalysis
            from .risk_metrics import RiskMetrics

            prices = self._fetch_prices()
            if prices is None or len(prices) < 30:
                return self._error("insufficient_price_data — need ≥ 30 trading days")

            current_price = float(prices.iloc[-1])

            vol = VolatilityModel(prices)
            annual_vol = vol.annual_volatility()
            annual_drift = vol.annual_drift()
            vol_regime = vol.regime()

            factor = FactorModel(self.ticker, prices)
            factor_exposures = factor.exposures()

            ta = TechnicalAnalysis(prices)
            ta_result = ta.composite()

            mc = QuantMonteCarlo(
                current_price=current_price,
                annual_drift=annual_drift,
                annual_vol=annual_vol,
                horizon_days=self.horizon_days,
                n_simulations=self.n_simulations,
            )
            mc_result = mc.run()

            rm = RiskMetrics(prices)
            var_95 = rm.var(confidence=0.95)
            cvar_95 = rm.cvar(confidence=0.95)
            sharpe = rm.sharpe()
            max_dd = rm.max_drawdown()

            return {
                "ticker": self.ticker,
                "current_price": round(current_price, 3),
                "annual_drift": round(annual_drift, 4),
                "annual_vol": round(annual_vol, 4),
                # Approximate implied vol from historical vol (HV * 1.05 is a common rule of thumb)
                "implied_vol": round(annual_vol * 1.05, 4),
                "horizon_days": self.horizon_days,
                "percentile_paths": mc_result["percentile_paths"],
                "probabilities": mc_result["probabilities"],
                "final_price_p5": mc_result["final_price_p5"],
                "final_price_p95": mc_result["final_price_p95"],
                "final_price_mean": mc_result["final_price_mean"],
                "var_95": round(var_95, 4),
                "cvar_95": round(cvar_95, 4),
                "sharpe": sharpe,
                "max_drawdown": max_dd,
                "signal_stability": round(ta_result["composite_score"], 3),
                "vol_regime": vol_regime,
                "factor_exposures": factor_exposures,
                "technical": ta_result,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
            }

        except Exception as e:
            logger.error(
                "QuantEngine.analyse failed for %s: %s", self.ticker, e, exc_info=True
            )
            return self._error(str(e))

    def prediction(self) -> dict:
        """Lightweight prediction — direction + quant confidence only.

        Returns a small dict suitable for inclusion in the merged prediction
        pipeline without carrying the full percentile path data.
        """
        try:
            result = self.analyse()
            if result.get("status") != "success":
                return result

            probs = result["probabilities"]
            prob_up = probs.get("up", 0.5)
            direction = "UP" if prob_up > 0.5 else "DOWN"
            # Scale 0–1: 0 = perfectly uncertain, 1 = certain
            quant_confidence = abs(prob_up - 0.5) * 2.0

            return {
                "ticker": self.ticker,
                "direction": direction,
                "quant_confidence": round(quant_confidence, 3),
                "vol_regime": result["vol_regime"],
                "var_95": result["var_95"],
                "cvar_95": result["cvar_95"],
                "sharpe": result["sharpe"],
                "technical_score": result["signal_stability"],
                "technical_signal": result["technical"].get("signal", "NEUTRAL"),
                "generated_at": result["generated_at"],
                "status": "success",
            }

        except Exception as e:
            logger.error(
                "QuantEngine.prediction failed for %s: %s", self.ticker, e, exc_info=True
            )
            return self._error(str(e))

    # ── Private helpers ──────────────────────────────────────────────────────

    def _fetch_prices(self) -> Optional[object]:
        """Fetch 1 year of daily closing prices via yfinance (already in requirements.txt)."""
        try:
            import yfinance as yf

            hist = yf.Ticker(self.ticker).history(period="1y")
            if hist.empty:
                logger.warning("yfinance returned empty history for %s", self.ticker)
                return None
            return hist["Close"].dropna()
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", self.ticker, e)
            return None

    def _error(self, reason: str) -> dict:
        return {
            "ticker": self.ticker,
            "status": "error",
            "error": reason,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
