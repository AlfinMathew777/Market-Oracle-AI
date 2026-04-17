"""Analyst recommendations signal via yfinance.

Produces two types of DataPoints per ticker:
  1. analyst_consensus — current consensus (strong_buy / buy / hold / sell / strong_sell)
  2. analyst_upgrade / analyst_downgrade — rating changes in the last 30 days

Both are available for free through yfinance (Yahoo Finance) with no API key.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from data_sources.base import DataPoint, DataSource

logger = logging.getLogger(__name__)

# More analysts = higher confidence (caps at 0.8)
_MAX_ANALYST_COUNT_FOR_FULL_CONFIDENCE = 20

# Weights for consensus calculation: strong_buy=+0.9, buy=+0.6, hold=0, sell=-0.6, strong_sell=-0.9
_CONSENSUS_WEIGHTS = {
    "strongBuy": 0.9,
    "buy": 0.6,
    "hold": 0.0,
    "sell": -0.6,
    "strongSell": -0.9,
}


class AnalystRecommendations(DataSource):
    """Wall Street / broker analyst recommendations from Yahoo Finance via yfinance."""

    name = "analyst_recommendations"
    _cache_ttl_seconds = 21600  # 6 hours — recommendations don't change often

    async def fetch(self, ticker: str, upgrade_window_days: int = 30) -> list[DataPoint]:
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, self._fetch_sync, ticker)
        except Exception as e:
            logger.warning("AnalystRecommendations yfinance failed for %s: %s", ticker, e)
            return []

        if not data:
            return []

        points: list[DataPoint] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=upgrade_window_days)

        # ── Current consensus ─────────────────────────────────────────────────
        summary = data.get("summary")
        if summary:
            point = self._build_consensus(ticker, summary)
            if point:
                points.append(point)

        # ── Recent upgrades / downgrades ──────────────────────────────────────
        upgrades_df = data.get("upgrades_downgrades")
        if upgrades_df is not None and not upgrades_df.empty:
            for idx, row in upgrades_df.iterrows():
                ts = _to_utc_datetime(idx)
                if ts is None or ts < cutoff:
                    continue
                point = self._build_upgrade_point(ticker, ts, row)
                if point:
                    points.append(point)

        logger.info("AnalystRecommendations: %d points for %s", len(points), ticker)
        return points

    @staticmethod
    def _fetch_sync(ticker: str) -> Optional[dict[str, Any]]:
        import yfinance as yf

        try:
            stock = yf.Ticker(ticker)
            return {
                "summary": stock.recommendations_summary,
                "upgrades_downgrades": stock.upgrades_downgrades,
            }
        except Exception as e:
            logger.debug("yfinance Ticker(%s) failed: %s", ticker, e)
            return None

    @staticmethod
    def _build_consensus(
        ticker: str, summary: Any
    ) -> Optional[DataPoint]:
        if summary is None or summary.empty:
            return None

        try:
            latest = summary.iloc[0]
        except (IndexError, AttributeError):
            return None

        totals = {k: int(latest.get(k, 0) or 0) for k in _CONSENSUS_WEIGHTS}
        total_analysts = sum(totals.values())
        if total_analysts == 0:
            return None

        weighted = sum(totals[k] * w for k, w in _CONSENSUS_WEIGHTS.items())
        consensus_signal = weighted / total_analysts
        confidence = min(0.80, total_analysts / _MAX_ANALYST_COUNT_FOR_FULL_CONFIDENCE)

        return DataPoint(
            source="analyst_recommendations",
            ticker=ticker,
            timestamp=datetime.now(timezone.utc),
            category="analyst_consensus",
            signal_strength=max(-1.0, min(1.0, consensus_signal)),
            confidence=confidence,
            raw_data={
                "strong_buy": totals["strongBuy"],
                "buy": totals["buy"],
                "hold": totals["hold"],
                "sell": totals["sell"],
                "strong_sell": totals["strongSell"],
                "total_analysts": total_analysts,
            },
            summary=(
                f"{ticker}: {total_analysts} analysts — "
                f"SB:{totals['strongBuy']} B:{totals['buy']} "
                f"H:{totals['hold']} S:{totals['sell']} SS:{totals['strongSell']} "
                f"(signal: {consensus_signal:+.2f})"
            ),
        )

    @staticmethod
    def _build_upgrade_point(
        ticker: str, ts: datetime, row: Any
    ) -> Optional[DataPoint]:
        action = str(row.get("Action", "")).lower()
        firm = str(row.get("Firm", "Analyst"))
        from_grade = str(row.get("FromGrade", ""))
        to_grade = str(row.get("ToGrade", ""))

        if "up" in action:
            signal, category = 0.50, "analyst_upgrade"
        elif "down" in action:
            signal, category = -0.50, "analyst_downgrade"
        else:
            return None  # "Initiated", "Reiterated", etc. — skip ambiguous

        return DataPoint(
            source="analyst_recommendations",
            ticker=ticker,
            timestamp=ts,
            category=category,
            signal_strength=signal,
            confidence=0.60,
            raw_data={
                "firm": firm,
                "from_grade": from_grade,
                "to_grade": to_grade,
                "action": action,
            },
            summary=(
                f"{ticker}: {firm} {action} "
                f"({from_grade} → {to_grade})"
            ),
        )


def _to_utc_datetime(idx: Any) -> Optional[datetime]:
    try:
        import pandas as pd

        if isinstance(idx, pd.Timestamp):
            dt = idx.to_pydatetime()
        elif isinstance(idx, datetime):
            dt = idx
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
