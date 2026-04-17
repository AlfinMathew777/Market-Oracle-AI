"""ASX company announcement scraper — highest signal-to-effort data source.

Scrapes ASX's public announcement feed for a ticker and classifies each
announcement's headline into a directional signal.

ASX publishes all announcements at:
  https://www.asx.com.au/asx/v2/statistics/announcements.do?by=asxCode&asxCode={CODE}

This is HTML (no JSON API on the free tier), so we use BeautifulSoup.
Price-sensitive announcements are flagged by ASX and carry higher confidence.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from data_sources.base import DataPoint, DataSource

logger = logging.getLogger(__name__)

# ASX announcement headline patterns → (category, signal_strength)
# Matched in order — first match wins.
_PATTERNS: list[tuple[str, str, float]] = [
    ("trading halt",       "trading_halt",     -0.70),
    ("suspension",         "trading_halt",     -0.65),
    ("profit upgrade",     "profit_upgrade",    0.65),
    ("earnings upgrade",   "profit_upgrade",    0.60),
    ("positive guidance",  "profit_upgrade",    0.55),
    ("profit downgrade",   "profit_downgrade", -0.65),
    ("earnings downgrade", "profit_downgrade", -0.60),
    ("negative guidance",  "profit_downgrade", -0.55),
    ("on-market buyback",  "buyback",           0.45),
    ("share buyback",      "buyback",           0.40),
    ("buyback",            "buyback",           0.35),
    ("acquisition",        "acquisition",       0.20),
    ("takeover",           "acquisition",       0.25),
    ("merger",             "acquisition",       0.20),
    ("dividend",           "dividend",          0.30),
    ("distribution",       "dividend",          0.25),
    ("ceo resignation",    "ceo_change",       -0.40),
    ("managing director",  "ceo_change",       -0.20),
    ("ceo appointment",    "ceo_change",       -0.10),
    ("quarterly report",   "quarterly",         0.05),
    ("quarterly activities","quarterly",        0.05),
    ("appendix 4c",        "quarterly",         0.05),
    ("substantial holder", "substantial_holder", 0.10),
    ("ceasing to be",      "substantial_holder",-0.10),
]

_ASX_ANN_URL = (
    "https://www.asx.com.au/asx/v2/statistics/announcements.do"
    "?by=asxCode&asxCode={code}&count=25"
)
_TIMEOUT = 12.0
_HEADERS = {"User-Agent": "MarketOracleAI/1.0 (research; contact: admin@marketoracle.ai)"}


class ASXAnnouncements(DataSource):
    """Scrape ASX announcement headlines and produce directional signals."""

    name = "asx_announcements"
    _cache_ttl_seconds = 600  # 10 min — announcements are time-sensitive

    async def fetch(self, ticker: str, days_back: int = 7) -> list[DataPoint]:
        asx_code = ticker.replace(".AX", "").upper()
        url = _ASX_ANN_URL.format(code=asx_code)
        cutoff = datetime.now() - timedelta(days=days_back)

        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning("ASX announcements HTTP %s for %s", e.response.status_code, ticker)
            return []
        except Exception as e:
            logger.warning("ASX announcements fetch failed for %s: %s", ticker, e)
            return []

        return self._parse_html(resp.text, ticker, cutoff)

    def _parse_html(
        self, html: str, ticker: str, cutoff: datetime
    ) -> list[DataPoint]:
        soup = BeautifulSoup(html, "html.parser")
        points: list[DataPoint] = []

        # ASX page uses a table for announcements; rows contain date + headline.
        # Selector is intentionally broad to survive minor ASX redesigns.
        rows = soup.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            date_text = cells[0].get_text(strip=True)
            headline = cells[2].get_text(strip=True)
            row_html = str(row).lower()
            is_price_sensitive = "pricesensitive" in row_html or "price sensitive" in row_html

            # Some cells have icons/links but no text — skip
            if not headline or len(headline) < 5:
                continue

            ann_date = self._parse_date(date_text)
            if ann_date is None or ann_date < cutoff:
                continue

            category, signal = self._classify(headline, is_price_sensitive)
            confidence = 0.80 if is_price_sensitive else 0.50

            points.append(DataPoint(
                source=self.name,
                ticker=ticker,
                timestamp=ann_date,
                category=category,
                signal_strength=signal,
                confidence=confidence,
                raw_data={
                    "headline": headline,
                    "price_sensitive": is_price_sensitive,
                    "asx_code": ticker.replace(".AX", ""),
                },
                summary=(
                    f"{ticker} [{category}]: {headline[:100]}"
                    + (" [PRICE SENSITIVE]" if is_price_sensitive else "")
                ),
            ))

        logger.info(
            "ASX announcements: %d points for %s (%d rows scanned)",
            len(points), ticker, len(rows),
        )
        return points

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        for fmt in ("%d/%m/%Y", "%d %b %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text.strip(), fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _classify(headline: str, is_price_sensitive: bool) -> tuple[str, float]:
        h = headline.lower()
        for keyword, category, base_signal in _PATTERNS:
            if keyword in h:
                signal = base_signal * 1.25 if is_price_sensitive else base_signal
                return category, max(-1.0, min(1.0, signal))
        # Price-sensitive announcements with unknown category still carry mild signal
        if is_price_sensitive:
            return "price_sensitive_other", 0.10
        return "other", 0.0

    async def health_check(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=_HEADERS) as client:
                resp = await client.head(
                    "https://www.asx.com.au/asx/v2/statistics/todayAnns.do"
                )
            return {"status": "ok" if resp.status_code < 500 else "degraded", "source": self.name}
        except Exception as e:
            return {"status": "unhealthy", "source": self.name, "error": str(e)}
