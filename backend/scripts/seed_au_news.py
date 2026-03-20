#!/usr/bin/env python
"""Seed Australian news from RSS feeds into Redis every 15 minutes.

Aggregates 25 Australian financial/geopolitical feeds + 10 global sources.
Called by Render cron: `cd backend && python scripts/seed_au_news.py`
"""

import asyncio
import sys
import os
import time
import hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
import httpx
import xml.etree.ElementTree as ET

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_au_news")

CACHE_KEY = "news:australia:v1"
LOCK_KEY  = "seed:news:lock"
CACHE_TTL = 900  # 15 minutes
MAX_ITEMS_PER_FEED = 5
MAX_AGE_HOURS = 48

# Australian + global financial/geopolitical RSS feeds
RSS_FEEDS = [
    # Australian financial
    {"url": "https://www.afr.com/rss",                          "source": "AFR",           "region": "AU"},
    {"url": "https://www.smh.com.au/rss/business.xml",          "source": "SMH Business",  "region": "AU"},
    {"url": "https://www.abc.net.au/news/feed/2942460/rss.xml", "source": "ABC Business",  "region": "AU"},
    {"url": "https://stockhead.com.au/feed/",                   "source": "Stockhead",     "region": "AU"},
    {"url": "https://www.miningweekly.com/rss",                 "source": "Mining Weekly", "region": "AU"},
    {"url": "https://www.theaustralian.com.au/feed",            "source": "The Australian","region": "AU"},
    {"url": "https://www.businessinsider.com.au/feed",          "source": "BI Australia",  "region": "AU"},
    {"url": "https://www.rba.gov.au/rss/rss-cb-media-releases.xml", "source": "RBA",       "region": "AU"},
    {"url": "https://www.asic.gov.au/about-asic/news-centre/rss/", "source": "ASIC",       "region": "AU"},
    {"url": "https://www.resourcesregulator.nsw.gov.au/rss",    "source": "NSW Resources", "region": "AU"},
    # Commodities / global
    {"url": "https://www.mining.com/feed/",                     "source": "Mining.com",    "region": "GLOBAL"},
    {"url": "https://oilprice.com/rss/main",                    "source": "OilPrice",      "region": "GLOBAL"},
    {"url": "https://www.reuters.com/tools/rss?type=article&channel=businessNews", "source": "Reuters Business", "region": "GLOBAL"},
    {"url": "https://feeds.ft.com/rss/home/asia-pacific",       "source": "FT Asia",       "region": "GLOBAL"},
    # Geopolitical
    {"url": "https://www.aljazeera.com/xml/rss/all.xml",        "source": "Al Jazeera",    "region": "GEO"},
    {"url": "https://www.cfr.org/rss.xml",                      "source": "CFR",           "region": "GEO"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",      "source": "BBC World",     "region": "GEO"},
]


async def fetch_feed(client: httpx.AsyncClient, feed: dict) -> list:
    """Fetch and parse a single RSS feed. Returns list of article dicts."""
    try:
        r = await client.get(feed["url"], timeout=8.0, follow_redirects=True)
        if r.status_code != 200:
            return []

        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        articles = []
        for item in items[:MAX_ITEMS_PER_FEED]:
            title = (item.findtext("title") or item.findtext("atom:title", namespaces=ns) or "").strip()
            link  = (item.findtext("link")  or item.findtext("atom:link",  namespaces=ns) or "").strip()
            desc  = (item.findtext("description") or item.findtext("atom:summary", namespaces=ns) or "").strip()
            pub   = (item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or "").strip()

            if not title:
                continue

            articles.append({
                "id":      hashlib.md5(link.encode()).hexdigest()[:12],
                "title":   title,
                "url":     link,
                "summary": desc[:200] if desc else "",
                "source":  feed["source"],
                "region":  feed["region"],
                "pubDate": pub,
                "fetchedAt": int(time.time()),
            })
        return articles

    except Exception as e:
        logger.debug("Feed %s failed: %s", feed["source"], e)
        return []


async def main():
    from services.redis_client import cache_set, acquire_lock, release_lock

    if not await acquire_lock(LOCK_KEY, ttl=120):
        logger.info("Another seed_au_news is running — skipping")
        return

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "AussieIntel/1.0 news-aggregator"},
            limits=httpx.Limits(max_connections=20),
        ) as client:
            tasks = [fetch_feed(client, feed) for feed in RSS_FEEDS]
            results = await asyncio.gather(*tasks)

        all_articles = []
        for batch in results:
            all_articles.extend(batch)

        # Deduplicate by id
        seen = set()
        unique = []
        for a in all_articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)

        # Sort by fetch time (newest first)
        unique.sort(key=lambda a: a["fetchedAt"], reverse=True)

        await cache_set(CACHE_KEY, unique, ttl=CACHE_TTL)
        logger.info("Seeded %d articles from %d feeds", len(unique), len(RSS_FEEDS))

    except Exception as e:
        logger.error("seed_au_news failed: %s", e)
        sys.exit(1)
    finally:
        await release_lock(LOCK_KEY)


if __name__ == "__main__":
    asyncio.run(main())
