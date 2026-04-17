"""Reddit retail sentiment signal for ASX tickers.

Monitors r/ASX_Bets, r/AusFinance, and r/fiaustralia for mentions of a ticker
and scores sentiment based on keyword matching. Returns [] gracefully when
REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are not configured.

Requires asyncpraw:
  pip install asyncpraw>=7.7.0

Add to Railway env vars:
  REDDIT_CLIENT_ID=xxx
  REDDIT_CLIENT_SECRET=xxx
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from data_sources.base import DataPoint, DataSource

logger = logging.getLogger(__name__)

_SUBREDDITS = ["ASX_Bets", "AusFinance", "fiaustralia"]
_MIN_MENTIONS = 3       # below this, signal is too noisy
_MENTION_NORM = 20      # normalise volume signal to this count

_BULLISH_TERMS = [
    "moon", "buy", "long", "bullish", "undervalued", "rocket",
    "pump", "squeeze", "breakout", "strong buy", "accumulate",
]
_BEARISH_TERMS = [
    "short", "bearish", "sell", "dump", "overvalued", "crash",
    "bags", "baghold", "puts", "brick", "rekt",
]


def _reddit_configured() -> bool:
    return bool(os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"))


class RedditSentiment(DataSource):
    """Retail sentiment signal from ASX-focused Reddit communities."""

    name = "reddit_sentiment"
    _cache_ttl_seconds = 1800  # 30 min

    async def fetch(self, ticker: str, hours_back: int = 24) -> list[DataPoint]:
        if not _reddit_configured():
            logger.debug("Reddit not configured (REDDIT_CLIENT_ID missing) — skipping")
            return []

        try:
            return await self._fetch_async(ticker, hours_back)
        except Exception as e:
            logger.warning("RedditSentiment fetch failed for %s: %s", ticker, e)
            return []

    async def _fetch_async(self, ticker: str, hours_back: int) -> list[DataPoint]:
        import asyncpraw  # noqa: PLC0415 — optional dependency

        asx_code = ticker.replace(".AX", "").upper()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        reddit = asyncpraw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent="MarketOracleAI/1.0 (by /u/market_oracle_bot)",
        )

        total_mentions = 0
        bullish_count = 0
        bearish_count = 0

        try:
            for sub_name in _SUBREDDITS:
                sub = await reddit.subreddit(sub_name)
                async for submission in sub.search(
                    asx_code, time_filter="day", limit=50, sort="new"
                ):
                    created = datetime.fromtimestamp(
                        submission.created_utc, tz=timezone.utc
                    )
                    if created < cutoff:
                        continue

                    text = f"{submission.title} {submission.selftext}".lower()

                    # Confirm ticker is genuinely in the post (search can return false positives)
                    if asx_code.lower() not in text and f"${asx_code.lower()}" not in text:
                        continue

                    total_mentions += 1
                    bull = sum(1 for t in _BULLISH_TERMS if t in text)
                    bear = sum(1 for t in _BEARISH_TERMS if t in text)

                    if bull > bear:
                        bullish_count += 1
                    elif bear > bull:
                        bearish_count += 1
        finally:
            await reddit.close()

        if total_mentions < _MIN_MENTIONS:
            logger.debug(
                "RedditSentiment: only %d mentions for %s — below threshold",
                total_mentions, ticker,
            )
            return []

        net_sentiment = (bullish_count - bearish_count) / total_mentions
        # Volume is itself a signal (unusual attention ≠ zero direction)
        volume_confidence = min(0.70, total_mentions / _MENTION_NORM)

        return [DataPoint(
            source=self.name,
            ticker=ticker,
            timestamp=datetime.now(timezone.utc),
            category="retail_sentiment",
            signal_strength=max(-1.0, min(1.0, net_sentiment * 0.70)),
            confidence=volume_confidence,
            raw_data={
                "total_mentions": total_mentions,
                "bullish_mentions": bullish_count,
                "bearish_mentions": bearish_count,
                "window_hours": hours_back,
                "subreddits": _SUBREDDITS,
            },
            summary=(
                f"{ticker}: {total_mentions} Reddit mentions — "
                f"{bullish_count}B/{bearish_count}Be "
                f"(net sentiment: {net_sentiment:+.2f})"
            ),
        )]

    async def health_check(self) -> dict[str, Any]:
        if not _reddit_configured():
            return {
                "status": "unconfigured",
                "source": self.name,
                "reason": "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set",
            }
        return {"status": "ok", "source": self.name}
