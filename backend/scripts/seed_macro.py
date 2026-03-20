#!/usr/bin/env python
"""Seed macro data (FRED + yfinance macro) into Redis every hour.

Called by Render cron: `cd backend && python scripts/seed_macro.py`
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_macro")

MACRO_KEY        = "macro:fred:v1"
CONTEXT_KEY      = "macro:context:v1"
CHINA_DEMAND_KEY = "signal:china:steel"
LOCK_KEY         = "seed:macro:lock"
CACHE_TTL        = 3600  # 1 hour


async def main():
    from services.redis_client import cache_set, acquire_lock, release_lock
    from services.fred_service import get_all_australian_macro
    from services.macro_service import MacroService

    if not await acquire_lock(LOCK_KEY, ttl=120):
        logger.info("Another seed_macro is running — skipping")
        return

    try:
        loop = asyncio.get_event_loop()

        # FRED Australian macro series
        logger.info("Fetching FRED macro data...")
        fred_data = await loop.run_in_executor(None, get_all_australian_macro)
        if fred_data.get("status") == "success" and fred_data.get("data"):
            await cache_set(MACRO_KEY, fred_data["data"], ttl=CACHE_TTL)
            logger.info("Seeded %d FRED series to Redis", len(fred_data["data"]))
        else:
            logger.warning("FRED returned no data: %s", fred_data.get("message", "unknown"))

        # Macro context (AUD/USD, iron ore spot, ASX 200)
        logger.info("Fetching macro context...")
        macro = MacroService()
        context = await loop.run_in_executor(None, macro.get_macro_context)
        if context:
            await cache_set(CONTEXT_KEY, context, ttl=CACHE_TTL)
            logger.info("Seeded macro context to Redis")

        # China demand signal (GDELT sentiment)
        logger.info("Fetching China demand signal...")
        from services.china_demand_service import _fetch_live_signal
        china_signal = await loop.run_in_executor(None, _fetch_live_signal)
        if china_signal.get("status") == "success":
            await cache_set(CHINA_DEMAND_KEY, china_signal, ttl=CACHE_TTL)
            logger.info("Seeded China demand signal: %s", china_signal.get("sentiment"))

    except Exception as e:
        logger.error("seed_macro failed: %s", e)
        sys.exit(1)
    finally:
        await release_lock(LOCK_KEY)


if __name__ == "__main__":
    asyncio.run(main())
