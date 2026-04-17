"""Abstract base class and shared DataPoint type for all data sources."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Module-level in-memory TTL cache — fallback when Redis is unavailable.
# Structure: key → (value, expire_timestamp)
_mem_cache: dict[str, tuple[Any, float]] = {}


def _mem_get(key: str) -> Optional[Any]:
    entry = _mem_cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        del _mem_cache[key]
        return None
    return value


def _mem_set(key: str, value: Any, ttl_seconds: int) -> None:
    _mem_cache[key] = (value, time.monotonic() + ttl_seconds)


@dataclass
class DataPoint:
    """Standardised signal from any alternative data source."""

    source: str                 # e.g. "asx_announcements"
    ticker: Optional[str]       # ASX ticker, or None for macro-level signals
    timestamp: datetime         # When the underlying event occurred
    category: str               # e.g. "insider_buy", "dividend", "retail_sentiment"
    signal_strength: float      # -1.0 (bearish) to +1.0 (bullish)
    confidence: float           # 0.0 to 1.0
    raw_data: dict[str, Any]    # Source-specific payload (not logged)
    summary: str                # Human-readable one-liner for agent context

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ticker": self.ticker,
            "timestamp": self.timestamp.isoformat(),
            "category": self.category,
            "signal_strength": round(self.signal_strength, 3),
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
        }


class DataSource(ABC):
    """Abstract base for all alternative data sources."""

    name: str = "base"
    _cache_ttl_seconds: int = 900  # 15 min default

    @abstractmethod
    async def fetch(self, ticker: str, **kwargs) -> list[DataPoint]:
        """Fetch data points for a ticker. Must not raise — return [] on failure."""

    async def fetch_cached(self, ticker: str, **kwargs) -> list[DataPoint]:
        """
        Fetch with two-tier caching: in-memory first, then Redis.
        Always degrades gracefully — returns [] on any error.
        """
        cache_key = f"datasource:{self.name}:{ticker}"

        # 1. In-memory cache (hot path — no I/O)
        cached = _mem_get(cache_key)
        if cached is not None:
            return cached

        # 2. Redis cache (warm path)
        try:
            from services.redis_client import cache_get
            redis_cached = await cache_get(cache_key)
            if redis_cached is not None:
                points = [DataPoint(**dp) for dp in redis_cached]
                _mem_set(cache_key, points, ttl_seconds=min(self._cache_ttl_seconds, 300))
                return points
        except Exception as e:
            logger.debug("%s Redis cache_get failed (non-fatal): %s", self.name, e)

        # 3. Live fetch
        try:
            points = await self.fetch(ticker, **kwargs)
        except Exception as e:
            logger.error("%s fetch raised unexpectedly for %s: %s", self.name, ticker, e)
            points = []

        # Store in both layers
        _mem_set(cache_key, points, ttl_seconds=self._cache_ttl_seconds)
        try:
            from services.redis_client import cache_set
            serialisable = [p.to_dict() for p in points]
            await cache_set(cache_key, serialisable, ttl=self._cache_ttl_seconds)
        except Exception as e:
            logger.debug("%s Redis cache_set failed (non-fatal): %s", self.name, e)

        return points

    async def health_check(self) -> dict[str, Any]:
        """Override in subclasses to ping the underlying source."""
        return {"status": "ok", "source": self.name}
