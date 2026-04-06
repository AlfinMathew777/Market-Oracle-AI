"""Technical analysis indicators — RSI, MACD, Bollinger Bands, SMA trend.

All implemented from first principles using numpy/pandas so no extra
dependencies are required beyond what is already in requirements.txt.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """Computes classic TA indicators and a composite directional score."""

    def __init__(self, prices) -> None:
        self._prices = prices

    # ── Individual indicators ────────────────────────────────────────────────

    def rsi(self, window: int = 14) -> float:
        """Wilder RSI (0–100). > 70 = overbought, < 30 = oversold."""
        try:
            delta = self._prices.diff()
            gain = delta.clip(lower=0).rolling(window).mean()
            loss = (-delta.clip(upper=0)).rolling(window).mean()
            rs = gain / loss.replace(0, float("nan"))
            rsi_series = 100.0 - (100.0 / (1.0 + rs))
            val = float(rsi_series.iloc[-1])
            return round(val, 1) if not np.isnan(val) else 50.0
        except Exception as e:
            logger.warning("RSI failed: %s", e)
            return 50.0

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
        """MACD line, signal line, and histogram."""
        try:
            ema_fast = self._prices.ewm(span=fast, adjust=False).mean()
            ema_slow = self._prices.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=signal, adjust=False).mean()
            histogram = macd_line - signal_line
            return {
                "macd": round(float(macd_line.iloc[-1]), 4),
                "signal": round(float(signal_line.iloc[-1]), 4),
                "histogram": round(float(histogram.iloc[-1]), 4),
                "bullish": bool(float(histogram.iloc[-1]) > 0),
            }
        except Exception as e:
            logger.warning("MACD failed: %s", e)
            return {"macd": 0.0, "signal": 0.0, "histogram": 0.0, "bullish": False}

    def bollinger_bands(self, window: int = 20, n_std: float = 2.0) -> dict:
        """Bollinger Bands: upper/middle/lower, %B position (0=at lower, 1=at upper)."""
        try:
            sma = self._prices.rolling(window).mean()
            std = self._prices.rolling(window).std()
            upper = sma + n_std * std
            lower = sma - n_std * std
            current = float(self._prices.iloc[-1])
            band_width = float(upper.iloc[-1] - lower.iloc[-1])
            pct_b = (
                (current - float(lower.iloc[-1])) / band_width
                if band_width > 0
                else 0.5
            )
            sma_val = float(sma.iloc[-1])
            squeeze = (band_width / sma_val) < 0.04 if sma_val > 0 else False
            return {
                "upper": round(float(upper.iloc[-1]), 3),
                "middle": round(sma_val, 3),
                "lower": round(float(lower.iloc[-1]), 3),
                "pct_b": round(pct_b, 3),
                "squeeze": squeeze,
            }
        except Exception as e:
            logger.warning("Bollinger Bands failed: %s", e)
            p = float(self._prices.iloc[-1])
            return {
                "upper": round(p * 1.04, 3),
                "middle": round(p, 3),
                "lower": round(p * 0.96, 3),
                "pct_b": 0.5,
                "squeeze": False,
            }

    def sma_trend(self) -> dict:
        """Price position relative to 20, 50, and 200-day SMAs."""
        try:
            current = float(self._prices.iloc[-1])
            result: dict = {}
            for period in (20, 50, 200):
                if len(self._prices) >= period:
                    sma_val = float(self._prices.rolling(period).mean().iloc[-1])
                    result[f"sma_{period}"] = round(sma_val, 3)
                    result[f"above_sma_{period}"] = current > sma_val
            return result
        except Exception as e:
            logger.warning("SMA trend failed: %s", e)
            return {}

    # ── Composite score ──────────────────────────────────────────────────────

    def composite(self) -> dict:
        """Weighted composite signal score (0–1).

        > 0.6 → BULLISH
        < 0.4 → BEARISH
        else  → NEUTRAL

        Weights: RSI 30 %, MACD 30 %, Bollinger %B 20 %, SMA trend 20 %
        """
        try:
            rsi_val = self.rsi()
            macd_data = self.macd()
            bb_data = self.bollinger_bands()
            sma_data = self.sma_trend()

            # RSI: oversold (<30) → bullish (0.8), overbought (>70) → bearish (0.2)
            if rsi_val < 30:
                rsi_score = 0.8
            elif rsi_val > 70:
                rsi_score = 0.2
            else:
                # Linear scale: 50 → 0.5, trending up = higher score
                rsi_score = 0.5 + (50.0 - rsi_val) / 100.0

            macd_score = 0.65 if macd_data["bullish"] else 0.35

            bb_score = float(bb_data["pct_b"])
            bb_score = max(0.0, min(1.0, bb_score))

            above_flags = [
                v for k, v in sma_data.items() if k.startswith("above_sma_")
            ]
            sma_score = sum(above_flags) / len(above_flags) if above_flags else 0.5

            composite_score = (
                rsi_score * 0.30
                + macd_score * 0.30
                + bb_score * 0.20
                + sma_score * 0.20
            )

            if composite_score > 0.6:
                signal = "BULLISH"
            elif composite_score < 0.4:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"

            return {
                "composite_score": round(composite_score, 3),
                "signal": signal,
                "rsi": rsi_val,
                "macd": macd_data,
                "bollinger": bb_data,
                "sma_trend": sma_data,
            }

        except Exception as e:
            logger.error("Technical composite failed: %s", e, exc_info=True)
            return {"composite_score": 0.5, "signal": "NEUTRAL", "rsi": 50.0}
