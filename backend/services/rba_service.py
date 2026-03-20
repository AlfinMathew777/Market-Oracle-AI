"""RBA (Reserve Bank of Australia) intelligence service.

Provides:
  - RBA cash rate (hardcoded current + FRED fallback)
  - 2026 meeting calendar (fixed dates, updated annually)
  - meeting-today flag (Redis-cached)
  - Last decision text (scraped from RBA RSS)
"""

import os
import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, List

import httpx
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# RBA cash rate — update this when RBA changes the rate
CURRENT_CASH_RATE = 4.10  # % — as of March 2026

# 2026 RBA Board meeting dates (published annually by RBA)
# Source: https://www.rba.gov.au/monetary-policy/rba-board-meetings/2026/
RBA_MEETING_DATES_2026: List[date] = [
    date(2026, 2, 17),
    date(2026, 4, 7),
    date(2026, 5, 19),
    date(2026, 7, 7),
    date(2026, 8, 18),
    date(2026, 9, 22),  # estimated
    date(2026, 11, 3),
    date(2026, 12, 8),
]

RBA_RSS_URL = "https://www.rba.gov.au/rss/rss-cb-media-releases.xml"


def get_rba_status() -> Dict[str, Any]:
    """Return RBA meeting calendar, current rate, and meeting-today flag."""
    today = date.today()

    # Meeting today?
    meeting_today = today in RBA_MEETING_DATES_2026

    # Next meeting
    future = [d for d in RBA_MEETING_DATES_2026 if d >= today]
    next_meeting = future[0].isoformat() if future else None

    # Meetings remaining this year
    remaining = len(future)

    # Try to get latest decision from RBA RSS
    last_decision = _fetch_last_rba_decision()

    return {
        "cash_rate":          CURRENT_CASH_RATE,
        "meeting_today":      meeting_today,
        "next_meeting":       next_meeting,
        "meetings_remaining": remaining,
        "meeting_dates_2026": [d.isoformat() for d in RBA_MEETING_DATES_2026],
        "last_decision":      last_decision,
        "checked_at":         datetime.now(timezone.utc).isoformat(),
    }


def _fetch_last_rba_decision() -> Dict[str, Any]:
    """Fetch latest RBA media release from RSS feed."""
    try:
        r = httpx.get(RBA_RSS_URL, timeout=5.0, follow_redirects=True)
        if r.status_code != 200:
            return {}
        root = ET.fromstring(r.text)
        item = root.find(".//item")
        if item is None:
            return {}
        return {
            "title":   (item.findtext("title") or "").strip(),
            "link":    (item.findtext("link") or "").strip(),
            "pubDate": (item.findtext("pubDate") or "").strip(),
            "summary": (item.findtext("description") or "")[:300].strip(),
        }
    except Exception as e:
        logger.debug("RBA RSS fetch failed: %s", e)
        return {}


def get_auto_simulation_tickers_for_rba() -> List[str]:
    """Return the tickers that should be auto-simulated on RBA meeting day."""
    return ["CBA.AX", "WBC.AX", "ANZ.AX", "NAB.AX"]
