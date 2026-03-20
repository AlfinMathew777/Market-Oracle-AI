#!/usr/bin/env python
"""Seed ASX prices into Redis every 5 minutes.

Called by Render cron: `cd backend && python scripts/seed_asx_prices.py`
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_asx_prices")

CACHE_KEY = "asx:prices:v1"
LOCK_KEY  = "seed:asx:lock"
CACHE_TTL = 300  # 5 minutes


async def main():
    from services.redis_client import cache_set, acquire_lock, release_lock
    from services.asx_service import ASXService

    if not await acquire_lock(LOCK_KEY, ttl=60):
        logger.info("Another seed_asx_prices is running — skipping")
        return

    try:
        logger.info("Fetching ASX prices via yfinance...")
        asx = ASXService()
        prices = asx.get_current_prices()

        if not prices:
            logger.warning("yfinance returned empty — not overwriting cache")
            return

        await cache_set(CACHE_KEY, prices, ttl=CACHE_TTL)
        logger.info("Seeded %d ASX prices to Redis", len(prices))

    except Exception as e:
        logger.error("seed_asx_prices failed: %s", e)
        sys.exit(1)
    finally:
        await release_lock(LOCK_KEY)


if __name__ == "__main__":
    asyncio.run(main())
