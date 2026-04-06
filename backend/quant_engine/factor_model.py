"""Factor model — market beta, momentum, and sector exposure for ASX tickers.

Uses only yfinance (already in requirements.txt). No additional dependencies.
Beta is computed via OLS regression against the ASX 200 index (^AXJO).
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

_ASX200_TICKER = "^AXJO"


class FactorModel:
    """Computes factor exposures for a ticker vs. ASX 200 and momentum signals."""

    def __init__(self, ticker: str, prices) -> None:
        self.ticker = ticker
        self._prices = prices
        self._returns = prices.pct_change().dropna()

    def market_beta(self) -> float:
        """OLS beta vs ASX 200. Falls back to 1.0 on any error."""
        try:
            import yfinance as yf

            market_hist = yf.Ticker(_ASX200_TICKER).history(period="1y")
            if market_hist.empty:
                return 1.0

            market_rets = market_hist["Close"].pct_change().dropna()
            common_idx = self._returns.index.intersection(market_rets.index)
            if len(common_idx) < 20:
                return 1.0

            s = self._returns.loc[common_idx].values
            m = market_rets.loc[common_idx].values

            cov_matrix = np.cov(s, m)
            cov_sm = float(cov_matrix[0, 1])
            var_m = float(np.var(m, ddof=1))
            if var_m <= 0:
                return 1.0
            return round(cov_sm / var_m, 3)

        except Exception as e:
            logger.warning("Beta calc failed for %s: %s", self.ticker, e)
            return 1.0

    def momentum(self) -> dict:
        """1-month and 3-month price momentum (cumulative return)."""
        try:
            n = len(self._prices)
            ret_1m = (
                float(self._prices.iloc[-1] / self._prices.iloc[-21] - 1)
                if n >= 21 else 0.0
            )
            ret_3m = (
                float(self._prices.iloc[-1] / self._prices.iloc[-63] - 1)
                if n >= 63 else 0.0
            )
            if ret_1m > 0 and ret_3m > 0:
                signal = "BULLISH"
            elif ret_1m < 0 and ret_3m < 0:
                signal = "BEARISH"
            else:
                signal = "MIXED"
            return {
                "mom_1m": round(ret_1m, 4),
                "mom_3m": round(ret_3m, 4),
                "signal": signal,
            }
        except Exception as e:
            logger.warning("Momentum failed for %s: %s", self.ticker, e)
            return {"mom_1m": 0.0, "mom_3m": 0.0, "signal": "NEUTRAL"}

    def exposures(self) -> list:
        """Return list of factor dicts for inclusion in the API response."""
        beta = self.market_beta()
        mom = self.momentum()

        if beta > 1.2:
            beta_interp = "High — amplifies market moves"
        elif beta < 0.8:
            beta_interp = "Low — relatively defensive"
        else:
            beta_interp = "Normal — tracks market closely"

        return [
            {
                "factor": "Market Beta",
                "exposure": beta,
                "interpretation": beta_interp,
            },
            {
                "factor": "1M Momentum",
                "exposure": round(mom["mom_1m"] * 100, 2),
                "interpretation": f"{mom['signal']} ({'+' if mom['mom_1m'] >= 0 else ''}{mom['mom_1m']*100:.1f}%)",
            },
            {
                "factor": "3M Momentum",
                "exposure": round(mom["mom_3m"] * 100, 2),
                "interpretation": f"{mom['signal']} ({'+' if mom['mom_3m'] >= 0 else ''}{mom['mom_3m']*100:.1f}%)",
            },
        ]
