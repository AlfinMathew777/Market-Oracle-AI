"""
ASX News Feed API Endpoints
---------------------------
Provides 20+ Australian market-relevant news topics.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.asx_news_aggregator import fetch_asx_news, get_aggregator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["news"])


@router.get("/api/news/asx")
async def get_asx_news(
    hours: int = Query(default=24, ge=1, le=72, description="Look back hours"),
    min_items: int = Query(default=20, ge=5, le=50, description="Minimum items"),
    max_items: int = Query(default=50, ge=10, le=100, description="Maximum items"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
):
    """
    Get aggregated ASX market news.

    Returns 20+ news topics affecting Australian stocks, grouped by category:
    - commodity: Iron ore, gold, oil, lithium prices
    - monetary: RBA interest rate decisions
    - currency: AUD/USD movements
    - earnings: Company results
    - corporate: M&A, management changes
    - geopolitical: China trade, global tensions
    - macro: GDP, employment, inflation
    - regulatory: ASIC, government policy
    - global: US Fed, international markets
    """
    try:
        news = await fetch_asx_news(
            hours=hours,
            min_items=min_items,
            max_items=max_items,
        )

        if category:
            news["items"] = [
                item for item in news["items"]
                if item["category"] == category.lower()
            ]

        return {
            "success": True,
            "news": news,
        }

    except Exception as e:
        logger.error("News fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to fetch news")


@router.get("/api/news/asx/categories")
async def get_news_categories():
    """Get available news categories."""
    return {
        "success": True,
        "categories": [
            {"id": "commodity",    "name": "Commodities",    "description": "Iron ore, gold, oil, lithium"},
            {"id": "monetary",     "name": "Monetary Policy","description": "RBA, interest rates"},
            {"id": "currency",     "name": "Currency",       "description": "AUD/USD movements"},
            {"id": "earnings",     "name": "Earnings",       "description": "Company results"},
            {"id": "corporate",    "name": "Corporate",      "description": "M&A, management"},
            {"id": "geopolitical", "name": "Geopolitical",   "description": "Trade, global tensions"},
            {"id": "macro",        "name": "Macro",          "description": "GDP, employment, inflation"},
            {"id": "regulatory",   "name": "Regulatory",     "description": "ASIC, policy"},
            {"id": "global",       "name": "Global",         "description": "US Fed, international"},
            {"id": "sector",       "name": "Sector",         "description": "Industry-specific"},
        ],
    }


@router.get("/api/news/asx/tickers")
async def get_tracked_tickers():
    """Get list of ASX tickers being tracked for news."""
    aggregator = get_aggregator()

    return {
        "success": True,
        "tickers": aggregator.ASX_TICKERS,
        "count": len(aggregator.ASX_TICKERS),
    }
