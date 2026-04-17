"""Aggregates all alternative data sources into a single composite signal.

Usage:
  from data_sources.aggregator import data_aggregator

  all_data = await data_aggregator.gather_all("BHP.AX", sector="Materials")
  composite = data_aggregator.aggregate_signal(all_data)
  # composite = {"signal": 0.35, "confidence": 0.72, "source_count": 8, ...}

The composite signal is injected into event_data before agents run, giving
each agent richer context without changing the core simulation pipeline.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from data_sources.asx_announcements import ASXAnnouncements
from data_sources.asic_insider import ASICInsider
from data_sources.analyst_recommendations import AnalystRecommendations
from data_sources.base import DataPoint
from data_sources.reddit_sentiment import RedditSentiment
from data_sources.rba_macro import RBAMacro

logger = logging.getLogger(__name__)

# Source reliability weights — must sum to ≤ 1.0 (remainder = uncertainty)
_SOURCE_WEIGHTS: dict[str, float] = {
    "asx_announcements":      0.30,   # Highest signal: direct corporate disclosures
    "asic_insider":           0.25,   # High signal: directors put money where mouths are
    "analyst_recommendations": 0.20,  # Medium: professional consensus
    "rba_macro":              0.15,   # Medium: systemic rate context
    "reddit_sentiment":       0.10,   # Lower: noisy retail, useful at extremes
}


class DataAggregator:
    """Combines signals from all five alternative data sources."""

    def __init__(self) -> None:
        self._sources = {
            "asx_announcements": ASXAnnouncements(),
            "asic_insider": ASICInsider(),
            "analyst_recommendations": AnalystRecommendations(),
            "rba_macro": RBAMacro(),
            "reddit_sentiment": RedditSentiment(),
        }

    async def gather_all(
        self,
        ticker: str,
        sector: str = "General",
        enabled_sources: Optional[list[str]] = None,
    ) -> dict[str, list[DataPoint]]:
        """
        Fetch from all (or a subset of) sources in parallel.

        Returns a dict mapping source_name → list[DataPoint].
        Failed sources return [] — never propagate exceptions.
        """
        sources = (
            {k: v for k, v in self._sources.items() if k in enabled_sources}
            if enabled_sources
            else self._sources
        )

        coros: dict[str, Any] = {}
        for name, source in sources.items():
            if name == "rba_macro":
                coros[name] = source.fetch_cached(ticker, sector=sector)
            else:
                coros[name] = source.fetch_cached(ticker)

        results = await asyncio.gather(*coros.values(), return_exceptions=True)

        output: dict[str, list[DataPoint]] = {}
        for name, result in zip(coros.keys(), results):
            if isinstance(result, BaseException):
                logger.error("Source %s raised unexpectedly: %s", name, result)
                output[name] = []
            else:
                output[name] = result  # type: ignore[assignment]

        total = sum(len(pts) for pts in output.values())
        logger.info(
            "AltData gathered for %s: %d total points across %d sources",
            ticker, total, len(output),
        )
        return output

    def aggregate_signal(
        self, data: dict[str, list[DataPoint]]
    ) -> dict[str, Any]:
        """
        Combine all DataPoints into a single weighted composite signal.

        Each source contributes according to _SOURCE_WEIGHTS.
        Within a source, individual confidence values act as sub-weights.

        Returns:
          signal         — composite directional signal (-1 to +1)
          confidence     — aggregate confidence (0 to 1)
          source_count   — total number of DataPoints across all sources
          per_source     — {source_name: n_points} for debug transparency
          summaries      — human-readable list for agent context injection
        """
        weighted_signal = 0.0
        total_weight = 0.0
        summaries: list[str] = []

        for source_name, points in data.items():
            if not points:
                continue

            source_weight = _SOURCE_WEIGHTS.get(source_name, 0.05)

            # Confidence-weighted average within this source
            conf_total = sum(p.confidence for p in points)
            if conf_total <= 0:
                continue

            source_signal = sum(p.signal_strength * p.confidence for p in points) / conf_total

            weighted_signal += source_signal * source_weight
            total_weight += source_weight

            for p in points:
                summaries.append(p.summary)

        if total_weight <= 0:
            return {
                "signal": 0.0,
                "confidence": 0.0,
                "source_count": 0,
                "per_source": {n: len(pts) for n, pts in data.items()},
                "summaries": [],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

        final_signal = weighted_signal / total_weight
        # Confidence is how much of the maximum total weight we captured
        final_confidence = min(1.0, total_weight)

        return {
            "signal": round(final_signal, 4),
            "confidence": round(final_confidence, 4),
            "source_count": sum(len(pts) for pts in data.values()),
            "per_source": {n: len(pts) for n, pts in data.items()},
            "summaries": summaries,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    async def health_check_all(self) -> dict[str, Any]:
        """Ping each source and return combined health status."""
        results = await asyncio.gather(
            *[src.health_check() for src in self._sources.values()],
            return_exceptions=True,
        )
        health: dict[str, Any] = {}
        for name, result in zip(self._sources.keys(), results):
            if isinstance(result, BaseException):
                health[name] = {"status": "error", "error": str(result)}
            else:
                health[name] = result  # type: ignore[assignment]

        all_ok = all(
            v.get("status") in ("ok", "unconfigured") for v in health.values()
        )
        return {
            "overall": "healthy" if all_ok else "degraded",
            "sources": health,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


# Module-level singleton — shared across all requests
data_aggregator = DataAggregator()
