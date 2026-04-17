"""RBA and ABS macro data signal — sector-aware rate sensitivity.

Wraps the existing rba_service and abs_service to produce directional
DataPoints based on the current RBA cash rate direction and sector sensitivity.

Sector sensitivity matrix:
  - Cash rate RISING → bullish for Banks (higher NIM), bearish for REITs + Utilities
  - Cash rate FALLING → bearish for Banks, bullish for REITs + Growth stocks

Meeting-day premium: confidence boosted on actual RBA decision days.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from data_sources.base import DataPoint, DataSource

logger = logging.getLogger(__name__)

# Sector → directional impact of a cash rate RISE (negate for a rate FALL)
_SECTOR_RATE_SENSITIVITY: dict[str, float] = {
    "Financials":        +0.30,   # Banks: higher NIM = revenue boost
    "Real Estate":       -0.40,   # REITs: higher debt costs + yield competition
    "Utilities":         -0.30,   # Rate-sensitive, bond-proxy
    "Materials":         -0.15,   # Higher AUD + cost of capital
    "Energy":            -0.10,   # Mild cost-of-capital headwind
    "Consumer Staples":  -0.10,   # Mild consumer spending dampener
    "Consumer Discretionary": -0.20,
    "Healthcare":        -0.05,   # Relatively insensitive
    "Technology":        -0.25,   # Growth stocks re-rate on higher discount rate
    "Lithium":           -0.20,   # Commodity + cost of expansion capital
    "Rare Earths":       -0.15,
    "General":            0.00,
}

# Last known RBA rate to detect direction changes (checked at fetch time)
_PREV_RATE_KEY = "rba_macro:prev_rate"


class RBAMacro(DataSource):
    """Macro signal derived from RBA cash rate level and direction."""

    name = "rba_macro"
    _cache_ttl_seconds = 21600  # 6 hours — cash rate changes rarely

    async def fetch(self, ticker: str, sector: str = "General", **kwargs) -> list[DataPoint]:  # type: ignore[override]
        try:
            rba_data = self._get_rba_status()
        except Exception as e:
            logger.warning("RBAMacro: rba_service unavailable: %s", e)
            return []

        cash_rate: float = rba_data.get("cash_rate", 0.0)
        meeting_today: bool = rba_data.get("meeting_today", False)
        last_decision: dict = rba_data.get("last_decision", {})

        rate_direction = self._detect_direction(last_decision)
        if rate_direction == 0:
            # No detectable change — emit a neutral context signal (low confidence)
            sector_exposure = _SECTOR_RATE_SENSITIVITY.get(sector, 0.0)
            if abs(sector_exposure) < 0.05:
                return []
            # Steady rate still matters as baseline context
            return [self._build_point(
                ticker=ticker,
                cash_rate=cash_rate,
                signal=sector_exposure * 0.30,  # muted when no change
                confidence=0.30,
                meeting_today=meeting_today,
                summary=(
                    f"RBA steady at {cash_rate:.2f}% — "
                    f"{sector} sector baseline sensitivity: {sector_exposure:+.2f}"
                ),
            )]

        sector_sensitivity = _SECTOR_RATE_SENSITIVITY.get(sector, 0.0)
        signal = sector_sensitivity * rate_direction  # +1 = rate rising, -1 = falling

        if abs(signal) < 0.05:
            return []  # Sector doesn't care about rate direction

        confidence = 0.65
        if meeting_today:
            confidence = 0.80  # Confirmed decision day

        direction_word = "rising" if rate_direction > 0 else "falling"
        return [self._build_point(
            ticker=ticker,
            cash_rate=cash_rate,
            signal=signal,
            confidence=confidence,
            meeting_today=meeting_today,
            summary=(
                f"RBA cash rate {direction_word} ({cash_rate:.2f}%) — "
                f"{sector} sector impact: {signal:+.2f}"
            ),
        )]

    @staticmethod
    def _get_rba_status() -> dict[str, Any]:
        from services.rba_service import get_rba_status
        return get_rba_status()

    @staticmethod
    def _detect_direction(last_decision: dict) -> int:
        """
        Detect rate direction from last RBA decision summary text.
        Returns +1 (rising), -1 (falling), 0 (unchanged/unknown).
        """
        if not last_decision:
            return 0
        title = (last_decision.get("title") or "").lower()
        summary = (last_decision.get("summary") or "").lower()
        text = f"{title} {summary}"

        if any(w in text for w in ["increase", "raised", "hike", "lifted"]):
            return +1
        if any(w in text for w in ["decrease", "reduced", "cut", "lowered", "eased"]):
            return -1
        return 0

    @staticmethod
    def _build_point(
        ticker: str,
        cash_rate: float,
        signal: float,
        confidence: float,
        meeting_today: bool,
        summary: str,
    ) -> DataPoint:
        return DataPoint(
            source="rba_macro",
            ticker=ticker,
            timestamp=datetime.now(timezone.utc),
            category="rba_cash_rate",
            signal_strength=max(-1.0, min(1.0, signal)),
            confidence=confidence,
            raw_data={
                "cash_rate": cash_rate,
                "meeting_today": meeting_today,
            },
            summary=summary,
        )

    async def health_check(self) -> dict[str, Any]:
        try:
            self._get_rba_status()
            return {"status": "ok", "source": self.name}
        except Exception as e:
            return {"status": "unhealthy", "source": self.name, "error": str(e)}
