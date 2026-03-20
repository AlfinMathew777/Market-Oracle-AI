"""China demand signal service.

Monitors GDELT sentiment across China steel/manufacturing/trade topics
and produces a composite signal used by agents and the MacroContext panel.

Redis key: signal:china:steel  (TTL 1h, seeded by seed_macro.py cron)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

# GDELT topics that proxy China steel / commodity demand
_TOPICS = [
    "China steel production",
    "China iron ore imports",
    "China manufacturing PMI",
    "China economic slowdown",
]


def get_china_demand_signal() -> Dict[str, Any]:
    """Return composite China demand sentiment from GDELT.

    Tries Redis cache first (seeded every hour by seed_macro.py).
    Falls back to live GDELT queries if cache is empty.
    """
    # 1. Try Redis cache
    try:
        from services.redis_client import _sync_get  # type: ignore
        cached = _sync_get("signal:china:steel")
        if cached:
            cached["from_cache"] = True
            return cached
    except Exception:
        pass  # Redis unavailable — fall through to live fetch

    # 2. Live GDELT queries (one per topic, averaged)
    return _fetch_live_signal()


def _fetch_live_signal() -> Dict[str, Any]:
    """Query GDELT for each China topic and average the tone scores."""
    from services.gdelt_service import get_gdelt_sentiment_score

    tones: list[float] = []
    article_counts: list[int] = []

    for topic in _TOPICS:
        try:
            result = get_gdelt_sentiment_score(topic, max_records=25)
            if result.get("status") in ("success", "no_data"):
                tones.append(result.get("avgtone", 0.0))
                article_counts.append(result.get("article_count", 0))
        except Exception as e:
            logger.debug("GDELT topic '%s' failed: %s", topic, e)

    if not tones:
        return _neutral_signal(source="no_data")

    avg_tone = sum(tones) / len(tones)
    total_articles = sum(article_counts)

    # Map GDELT tone (-10..+10) to demand signal
    # Negative tone = weak demand (bearish for iron ore / BHP / RIO)
    # Positive tone = strong demand (bullish)
    if avg_tone <= -2.0:
        sentiment = "weak"
        color = "red"
    elif avg_tone >= 2.0:
        sentiment = "strong"
        color = "green"
    else:
        sentiment = "neutral"
        color = "amber"

    return {
        "sentiment": sentiment,
        "avgtone": round(avg_tone, 2),
        "article_count": total_articles,
        "color": color,
        "label": f"China Demand: {sentiment.upper()}",
        "topics_queried": len(tones),
        "source": "GDELT DOC 2.0",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "status": "success",
    }


def _neutral_signal(source: str = "error") -> Dict[str, Any]:
    return {
        "sentiment": "neutral",
        "avgtone": 0.0,
        "article_count": 0,
        "color": "amber",
        "label": "China Demand: NEUTRAL",
        "topics_queried": 0,
        "source": source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "from_cache": False,
        "status": source,
    }
