#!/usr/bin/env python
"""Seed ACLED conflict events into Redis every 6 hours.

Called by Render cron: `cd backend && python scripts/seed_acled.py`
Stampede-protected: if another instance is already seeding, exits immediately.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_acled")

CACHE_KEY  = "acled:events:v1"
LOCK_KEY   = "seed:acled:lock"
CACHE_TTL  = 6 * 3600  # 6 hours


async def main():
    from services.redis_client import cache_get, cache_set, acquire_lock, release_lock
    from services.acled_service import ACLEDService

    # Stampede protection
    if not await acquire_lock(LOCK_KEY, ttl=300):
        logger.info("Another seed_acled is running — skipping")
        return

    try:
        logger.info("Fetching ACLED events...")
        acled = ACLEDService()
        geojson = acled.get_events()

        count = geojson.get("count", 0) or len(geojson.get("features", []))
        if count == 0:
            logger.warning("ACLED returned 0 events — not overwriting cache")
            return

        await cache_set(CACHE_KEY, geojson, ttl=CACHE_TTL)
        logger.info("Seeded %d ACLED events to Redis (TTL=%dh)", count, CACHE_TTL // 3600)

    except Exception as e:
        logger.error("seed_acled failed: %s", e)
        sys.exit(1)
    finally:
        await release_lock(LOCK_KEY)


if __name__ == "__main__":
    asyncio.run(main())
