"""ASIC / ASX insider transaction signal.

Uses yfinance's insider_transactions attribute to detect director buying or
selling. This is far simpler than PDF-parsing Appendix 3Y filings and covers
most of the signal.

Signal logic:
  - Net director BUY value (last 30 days) > $10k → bullish
  - Net director SELL value (last 30 days) > $10k → bearish
  - Multiple directors moving in the same direction amplifies signal
  - Options exercises excluded (not genuine conviction)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from data_sources.base import DataPoint, DataSource

logger = logging.getLogger(__name__)

_MIN_DOLLAR_THRESHOLD = 10_000   # below this, treat as noise
_MULTI_DIRECTOR_BOOST = 1.20     # 20% signal boost if ≥2 directors agree


class ASICInsider(DataSource):
    """Detect insider (director) buying/selling via yfinance insider_transactions."""

    name = "asic_insider"
    _cache_ttl_seconds = 3600  # 1 hour — insider data changes slowly

    async def fetch(self, ticker: str, days_back: int = 30) -> list[DataPoint]:
        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(None, self._fetch_sync, ticker, days_back)
        except Exception as e:
            logger.warning("ASICInsider yfinance call failed for %s: %s", ticker, e)
            return []

        if not raw:
            return []

        net_value, dir_buying, dir_selling = raw
        if abs(net_value) < _MIN_DOLLAR_THRESHOLD:
            return []

        is_bullish = net_value > 0
        base_signal = 0.70 if is_bullish else -0.70
        directors_same_dir = dir_buying if is_bullish else dir_selling

        if directors_same_dir >= 2:
            signal = base_signal * _MULTI_DIRECTOR_BOOST
        else:
            signal = base_signal

        signal = max(-1.0, min(1.0, signal))
        category = "insider_buy" if is_bullish else "insider_sell"
        direction_word = "buying" if is_bullish else "selling"

        return [DataPoint(
            source=self.name,
            ticker=ticker,
            timestamp=datetime.now(timezone.utc),
            category=category,
            signal_strength=signal,
            confidence=0.75,
            raw_data={
                "net_value_aud": net_value,
                "directors_buying": dir_buying,
                "directors_selling": dir_selling,
                "window_days": days_back,
            },
            summary=(
                f"{ticker}: Net insider {direction_word} "
                f"${abs(net_value):,.0f} over {days_back}d "
                f"({directors_same_dir} director{'s' if directors_same_dir != 1 else ''})"
            ),
        )]

    @staticmethod
    def _fetch_sync(ticker: str, days_back: int) -> tuple[float, int, int] | None:
        """
        Runs in a thread pool — yfinance is synchronous.

        Returns (net_value, directors_buying, directors_selling) or None.
        net_value > 0 means more buying than selling (in AUD).
        """
        import yfinance as yf

        try:
            stock = yf.Ticker(ticker)
            df = stock.insider_transactions
        except Exception as e:
            logger.debug("yfinance insider_transactions failed for %s: %s", ticker, e)
            return None

        if df is None or df.empty:
            return None

        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        # Normalise index to UTC-aware datetimes
        if df.index.tz is None:
            df = df.copy()
            df.index = df.index.tz_localize("UTC")
        recent = df[df.index >= cutoff]

        if recent.empty:
            return None

        net_value = 0.0
        directors_buying: set[str] = set()
        directors_selling: set[str] = set()

        for _, row in recent.iterrows():
            tx_type = str(row.get("Transaction", "")).lower()

            # Skip option exercises — not genuine conviction
            if "option" in tx_type or "exercise" in tx_type:
                continue

            shares = row.get("Shares", 0) or 0
            price = row.get("Value", None)
            insider = str(row.get("Insider", "unknown"))

            # yfinance Value column is sometimes the total transaction value
            tx_value: float
            if price is not None:
                tx_value = float(price)
            else:
                tx_value = 0.0

            if "sale" in tx_type or "sold" in tx_type or "sell" in tx_type:
                net_value -= abs(tx_value)
                directors_selling.add(insider)
            elif "purchase" in tx_type or "bought" in tx_type or "buy" in tx_type:
                net_value += abs(tx_value)
                directors_buying.add(insider)
            # Ambiguous transactions (e.g. "automatic") are skipped

        return net_value, len(directors_buying), len(directors_selling)

    async def health_check(self) -> dict[str, Any]:
        return {"status": "ok", "source": self.name, "backend": "yfinance"}
