"""Error memory — learns from prediction failures to improve future agents.

Stores wrong predictions per ticker and surfaces anti-patterns so agent
system prompts can explicitly avoid previously failed reasoning chains.

Usage::

    memory = ErrorMemory()
    memory.record_failure(
        ticker="BHP",
        predicted_direction="bullish",
        actual_direction="bearish",
        confidence=0.72,
        reasoning_summary="Iron ore volume up = demand up",
        causal_factors=["volume_misread", "AUD_FX_error"],
    )

    # Inject into agent prompt:
    anti_patterns = memory.get_anti_patterns("BHP")
    # → ["Iron ore volume up = demand up", …]
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FailedPrediction:
    ticker: str
    timestamp: str                  # ISO-8601 UTC
    predicted_direction: str        # "bullish" | "bearish" | "neutral"
    actual_direction: str
    confidence: float
    reasoning_summary: str
    causal_factors: List[str] = field(default_factory=list)


class ErrorMemory:
    """In-memory store of wrong predictions with anti-pattern extraction."""

    def __init__(self, max_per_ticker: int = 10) -> None:
        self.max_per_ticker = max_per_ticker
        self._failures: Dict[str, List[FailedPrediction]] = defaultdict(list)

    # ── Write API ─────────────────────────────────────────────────────────────

    def record_failure(
        self,
        ticker: str,
        predicted_direction: str,
        actual_direction: str,
        confidence: float,
        reasoning_summary: str,
        causal_factors: Optional[List[str]] = None,
    ) -> None:
        fp = FailedPrediction(
            ticker=ticker,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            predicted_direction=predicted_direction,
            actual_direction=actual_direction,
            confidence=confidence,
            reasoning_summary=reasoning_summary,
            causal_factors=causal_factors or [],
        )
        bucket = self._failures[ticker]
        bucket.append(fp)
        # Keep only the most recent N failures per ticker
        if len(bucket) > self.max_per_ticker:
            self._failures[ticker] = bucket[-self.max_per_ticker:]
        logger.info(
            "[ErrorMemory] Recorded failure for %s: predicted=%s actual=%s conf=%.2f",
            ticker,
            predicted_direction,
            actual_direction,
            confidence,
        )

    def clear_old_failures(self, days: int = 30) -> int:
        """Remove failures older than `days` days. Returns number removed."""
        from datetime import timedelta
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
        removed = 0
        for ticker in list(self._failures):
            before = len(self._failures[ticker])
            self._failures[ticker] = [
                fp for fp in self._failures[ticker]
                if datetime.fromisoformat(fp.timestamp) >= cutoff
            ]
            removed += before - len(self._failures[ticker])
            if not self._failures[ticker]:
                del self._failures[ticker]
        return removed

    # ── Read API ──────────────────────────────────────────────────────────────

    def get_anti_patterns(self, ticker: str) -> List[str]:
        """Return reasoning summaries that previously led to wrong predictions."""
        return [fp.reasoning_summary for fp in self._failures.get(ticker, [])]

    def get_failure_rate(self, ticker: str) -> float:
        """Returns failure count for ticker (absolute, not a ratio — ratio needs total)."""
        return float(len(self._failures.get(ticker, [])))

    def get_common_mistakes(self) -> Dict[str, int]:
        """Return causal factor → failure count across all tickers."""
        counts: Dict[str, int] = defaultdict(int)
        for failures in self._failures.values():
            for fp in failures:
                for factor in fp.causal_factors:
                    counts[factor] += 1
        return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))

    def export_for_training(self) -> List[Dict]:
        """Serialise all failures for future fine-tuning."""
        return [
            asdict(fp)
            for failures in self._failures.values()
            for fp in failures
        ]

    def get_prompt_injection(self, ticker: str) -> str:
        """Return a formatted string ready to inject into an agent system prompt."""
        patterns = self.get_anti_patterns(ticker)
        if not patterns:
            return ""
        numbered = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(patterns[:5]))
        return (
            f"AVOID these reasoning patterns that previously failed for {ticker}:\n"
            + numbered
        )
