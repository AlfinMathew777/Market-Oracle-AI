"""
ASX News Aggregator
-------------------
Aggregates news from multiple sources to provide 20+ relevant topics
affecting the Australian stock market.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import aiohttp

logger = logging.getLogger(__name__)


class NewsCategory(str, Enum):
    """Categories of market-moving news."""

    COMMODITY = "commodity"           # Iron ore, gold, oil, lithium
    MONETARY_POLICY = "monetary"      # RBA, interest rates
    CURRENCY = "currency"             # AUD/USD movements
    EARNINGS = "earnings"             # Company results
    CORPORATE = "corporate"           # M&A, management, guidance
    GEOPOLITICAL = "geopolitical"     # Trade wars, China relations
    SECTOR = "sector"                 # Sector-specific news
    MACRO = "macro"                   # GDP, employment, inflation
    REGULATORY = "regulatory"         # ASIC, government policy
    GLOBAL = "global"                 # US Fed, global markets


@dataclass
class NewsItem:
    """Single news item."""

    headline: str
    summary: str
    source: str
    published_at: datetime
    category: NewsCategory
    tickers: List[str] = field(default_factory=list)
    relevance_score: float = 0.5
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
            "category": self.category.value,
            "tickers": self.tickers,
            "relevance_score": round(self.relevance_score, 2),
            "url": self.url,
        }


@dataclass
class AggregatedNews:
    """Collection of aggregated news."""

    items: List[NewsItem]
    fetch_time: datetime
    sources_used: List[str]
    total_raw: int
    total_filtered: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": [item.to_dict() for item in self.items],
            "fetch_time": self.fetch_time.isoformat(),
            "sources_used": self.sources_used,
            "total_raw": self.total_raw,
            "total_filtered": self.total_filtered,
            "by_category": self._group_by_category(),
        }

    def _group_by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for item in self.items:
            cat = item.category.value
            counts[cat] = counts.get(cat, 0) + 1
        return counts


class ASXNewsAggregator:
    """
    Aggregates news from multiple sources for Australian market coverage.

    Sources:
    - MarketAux (primary)
    - Alpha Vantage News
    - Macro theme topics (RBA, AUD, commodities)
    """

    # ASX 50 market movers for broad coverage
    ASX_TICKERS = [
        # Miners (Big Iron)
        "BHP.AX", "RIO.AX", "FMG.AX", "MIN.AX", "S32.AX",
        # Banks (Big 4 + Macquarie)
        "CBA.AX", "NAB.AX", "WBC.AX", "ANZ.AX", "MQG.AX",
        # Energy
        "WDS.AX", "STO.AX", "ORG.AX",
        # Healthcare
        "CSL.AX", "COH.AX", "RMD.AX",
        # Retail
        "WOW.AX", "COL.AX", "WES.AX",
        # Tech
        "XRO.AX", "WTC.AX", "APX.AX", "REA.AX",
        # REITs
        "GMG.AX", "SCG.AX", "GPT.AX",
        # Rare Earth / Lithium
        "LYC.AX", "PLS.AX", "IGO.AX", "SYR.AX",
        # Telco / Utilities
        "TLS.AX", "TPG.AX",
        # Insurance
        "QBE.AX", "IAG.AX", "SUN.AX",
        # Gaming / Entertainment
        "ALL.AX", "TAH.AX",
        # Transport
        "QAN.AX", "TCL.AX",
    ]

    # Keywords for relevance scoring
    HIGH_RELEVANCE_KEYWORDS = [
        "ASX", "Australia", "RBA", "iron ore", "BHP", "Rio Tinto",
        "CBA", "Westpac", "NAB", "ANZ", "CSL", "Woodside",
        "AUD", "Sydney", "Melbourne", "Perth", "Queensland",
        "lithium", "rare earth", "LNG", "coal", "gold",
    ]

    def __init__(
        self,
        marketaux_api_key: Optional[str] = None,
        alphavantage_api_key: Optional[str] = None,
    ):
        self.marketaux_key = marketaux_api_key
        self.alphavantage_key = alphavantage_api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_all_news(
        self,
        hours: int = 24,
        min_items: int = 20,
        max_items: int = 50,
    ) -> AggregatedNews:
        """
        Fetch news from all sources and aggregate.

        Args:
            hours: Look back period in hours
            min_items: Minimum news items to return
            max_items: Maximum news items to return

        Returns:
            AggregatedNews with deduplicated, ranked items
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        sources_used: List[str] = []
        all_items: List[NewsItem] = []

        tasks = []

        if self.marketaux_key:
            tasks.append(self._fetch_marketaux(cutoff))
            sources_used.append("MarketAux")

        if self.alphavantage_key:
            tasks.append(self._fetch_alphavantage(cutoff))
            sources_used.append("AlphaVantage")

        # Always add macro themes
        tasks.append(self._fetch_macro_topics(cutoff))
        sources_used.append("MacroTopics")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error(f"News fetch error: {result}")
                continue
            if isinstance(result, list):
                all_items.extend(result)

        total_raw = len(all_items)

        all_items = self._deduplicate(all_items)
        all_items = self._score_relevance(all_items)
        all_items.sort(key=lambda x: (-x.relevance_score, x.published_at), reverse=False)
        all_items = sorted(all_items, key=lambda x: -x.relevance_score)
        all_items = all_items[:max_items]

        if len(all_items) < min_items:
            synthetic = self._generate_synthetic_topics(cutoff, min_items - len(all_items))
            all_items.extend(synthetic)

        return AggregatedNews(
            items=all_items,
            fetch_time=datetime.now(timezone.utc),
            sources_used=sources_used,
            total_raw=total_raw,
            total_filtered=len(all_items),
        )

    async def _fetch_marketaux(self, cutoff: datetime) -> List[NewsItem]:
        """Fetch from MarketAux API."""
        items: List[NewsItem] = []

        try:
            session = await self._get_session()

            # Batch tickers — MarketAux limits symbols per request
            ticker_batches = [
                self.ASX_TICKERS[i:i + 10]
                for i in range(0, len(self.ASX_TICKERS), 10)
            ]

            for batch in ticker_batches[:3]:  # Limit to 3 API calls
                params = {
                    "api_token": self.marketaux_key,
                    "symbols": ",".join(batch),
                    "filter_entities": "true",
                    "countries": "au",
                    "language": "en",
                    "limit": 20,
                    "published_after": cutoff.strftime("%Y-%m-%dT%H:%M:%S"),
                }

                async with session.get(
                    "https://api.marketaux.com/v1/news/all",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        for article in data.get("data", []):
                            try:
                                pub_time = datetime.fromisoformat(
                                    article["published_at"].replace("Z", "+00:00")
                                )

                                if pub_time < cutoff:
                                    continue

                                tickers = [
                                    e["symbol"] for e in article.get("entities", [])
                                    if e.get("symbol", "").endswith(".AX")
                                ]

                                items.append(NewsItem(
                                    headline=article.get("title", ""),
                                    summary=article.get("description", "")[:500],
                                    source="MarketAux",
                                    published_at=pub_time,
                                    category=self._categorize(article.get("title", "")),
                                    tickers=tickers,
                                    url=article.get("url"),
                                ))
                            except Exception as e:
                                logger.debug(f"Skip MarketAux article: {e}")
                                continue

                await asyncio.sleep(0.5)  # Rate limit

        except Exception as e:
            logger.error(f"MarketAux fetch failed: {e}")

        return items

    async def _fetch_alphavantage(self, cutoff: datetime) -> List[NewsItem]:
        """Fetch from Alpha Vantage News API."""
        items: List[NewsItem] = []

        try:
            session = await self._get_session()

            topics = ["mining", "australia", "iron ore", "lithium", "banking"]

            for topic in topics[:2]:  # Limit API calls
                params = {
                    "function": "NEWS_SENTIMENT",
                    "topics": topic,
                    "apikey": self.alphavantage_key,
                    "limit": 10,
                }

                async with session.get(
                    "https://www.alphavantage.co/query",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        for article in data.get("feed", []):
                            try:
                                time_str = article.get("time_published", "")
                                pub_time = datetime.strptime(
                                    time_str[:15], "%Y%m%dT%H%M%S"
                                ).replace(tzinfo=timezone.utc)

                                if pub_time < cutoff:
                                    continue

                                text = f"{article.get('title', '')} {article.get('summary', '')}"
                                if not any(
                                    kw in text.lower()
                                    for kw in ["australia", "asx", "aud", "sydney"]
                                ):
                                    continue

                                items.append(NewsItem(
                                    headline=article.get("title", ""),
                                    summary=article.get("summary", "")[:500],
                                    source="AlphaVantage",
                                    published_at=pub_time,
                                    category=self._categorize(article.get("title", "")),
                                    tickers=[],
                                    url=article.get("url"),
                                ))
                            except Exception as e:
                                logger.debug(f"Skip AlphaVantage article: {e}")
                                continue

                await asyncio.sleep(1)  # Rate limit

        except Exception as e:
            logger.error(f"AlphaVantage fetch failed: {e}")

        return items

    async def _fetch_macro_topics(self, cutoff: datetime) -> List[NewsItem]:
        """
        Generate macro theme placeholders for market context.
        These represent ongoing macro themes even without specific news.
        """
        now = datetime.now(timezone.utc)

        macro_themes = [
            {
                "headline": "Iron Ore Spot Price Movement",
                "summary": "Daily iron ore 62% Fe spot price impacts major ASX miners BHP, RIO, FMG",
                "category": NewsCategory.COMMODITY,
                "tickers": ["BHP.AX", "RIO.AX", "FMG.AX"],
            },
            {
                "headline": "AUD/USD Exchange Rate",
                "summary": "Australian dollar movement affects export revenues for resource companies",
                "category": NewsCategory.CURRENCY,
                "tickers": [],
            },
            {
                "headline": "RBA Interest Rate Outlook",
                "summary": "Reserve Bank of Australia monetary policy affects banks and housing-exposed stocks",
                "category": NewsCategory.MONETARY_POLICY,
                "tickers": ["CBA.AX", "NAB.AX", "WBC.AX", "ANZ.AX"],
            },
            {
                "headline": "China Economic Indicators",
                "summary": "China PMI, steel production, and property sector affect Australian commodity demand",
                "category": NewsCategory.MACRO,
                "tickers": ["BHP.AX", "RIO.AX", "FMG.AX", "MIN.AX"],
            },
            {
                "headline": "Lithium & Battery Metals Prices",
                "summary": "Spodumene and lithium carbonate prices affect Australian lithium miners",
                "category": NewsCategory.COMMODITY,
                "tickers": ["PLS.AX", "IGO.AX", "MIN.AX", "LYC.AX"],
            },
            {
                "headline": "Oil & LNG Prices",
                "summary": "Brent crude and LNG spot prices impact Woodside and Santos",
                "category": NewsCategory.COMMODITY,
                "tickers": ["WDS.AX", "STO.AX"],
            },
            {
                "headline": "US Federal Reserve Policy",
                "summary": "Fed rate decisions affect global risk sentiment and AUD",
                "category": NewsCategory.GLOBAL,
                "tickers": [],
            },
            {
                "headline": "Australian Employment Data",
                "summary": "Jobs data influences RBA policy and consumer-facing stocks",
                "category": NewsCategory.MACRO,
                "tickers": ["WOW.AX", "WES.AX", "COL.AX"],
            },
            {
                "headline": "Gold Price Movement",
                "summary": "Gold spot price affects Australian gold miners",
                "category": NewsCategory.COMMODITY,
                "tickers": ["NCM.AX", "NST.AX", "EVN.AX"],
            },
            {
                "headline": "ASX 200 Index Movement",
                "summary": "Broad market sentiment and index-level flows",
                "category": NewsCategory.MACRO,
                "tickers": [],
            },
            {
                "headline": "Australian Housing Market",
                "summary": "Property market data affects bank provisions and consumer sentiment",
                "category": NewsCategory.MACRO,
                "tickers": ["CBA.AX", "NAB.AX", "WBC.AX", "ANZ.AX"],
            },
            {
                "headline": "Copper Price Outlook",
                "summary": "Copper demand from China electrification affects Australian miners",
                "category": NewsCategory.COMMODITY,
                "tickers": ["BHP.AX", "S32.AX"],
            },
            {
                "headline": "Australian CPI Inflation",
                "summary": "Consumer price data shapes RBA rate path and retail sector outlook",
                "category": NewsCategory.MACRO,
                "tickers": ["WOW.AX", "COL.AX"],
            },
            {
                "headline": "China-Australia Trade Relations",
                "summary": "Trade policy developments affect commodity export volumes and prices",
                "category": NewsCategory.GEOPOLITICAL,
                "tickers": ["BHP.AX", "RIO.AX", "FMG.AX", "WDS.AX"],
            },
            {
                "headline": "ASX Healthcare Sector Watch",
                "summary": "CSL, Cochlear, ResMed sector performance and product pipeline",
                "category": NewsCategory.SECTOR,
                "tickers": ["CSL.AX", "COH.AX", "RMD.AX"],
            },
        ]

        return [
            NewsItem(
                headline=theme["headline"],
                summary=theme["summary"],
                source="MacroTheme",
                published_at=now,
                category=theme["category"],
                tickers=theme["tickers"],
                relevance_score=0.7,
            )
            for theme in macro_themes
        ]

    def _generate_synthetic_topics(
        self,
        cutoff: datetime,
        count: int,
    ) -> List[NewsItem]:
        """Generate synthetic topics to meet minimum coverage."""
        now = datetime.now(timezone.utc)

        synthetic = [
            NewsItem(
                headline="Australian Market Open",
                summary="ASX 200 trading session overview",
                source="Synthetic",
                published_at=now,
                category=NewsCategory.MACRO,
                relevance_score=0.5,
            ),
            NewsItem(
                headline="Commodity Price Update",
                summary="Daily commodity price movements affecting ASX miners",
                source="Synthetic",
                published_at=now,
                category=NewsCategory.COMMODITY,
                relevance_score=0.5,
            ),
            NewsItem(
                headline="Banking Sector Watch",
                summary="Big 4 banks sector performance and NIM outlook",
                source="Synthetic",
                published_at=now,
                category=NewsCategory.SECTOR,
                relevance_score=0.5,
            ),
        ]

        return synthetic[:count]

    def _categorize(self, headline: str) -> NewsCategory:
        """Categorize headline into news category."""
        h = headline.lower()

        if any(kw in h for kw in ["iron ore", "gold", "oil", "copper", "lithium", "coal", "lng"]):
            return NewsCategory.COMMODITY
        if any(kw in h for kw in ["rba", "interest rate", "rate cut", "rate hike"]):
            return NewsCategory.MONETARY_POLICY
        if any(kw in h for kw in ["aud", "australian dollar", "forex", "currency"]):
            return NewsCategory.CURRENCY
        if any(kw in h for kw in ["earnings", "profit", "revenue", "results", "eps"]):
            return NewsCategory.EARNINGS
        if any(kw in h for kw in ["merger", "acquisition", "takeover", "ceo", "board"]):
            return NewsCategory.CORPORATE
        if any(kw in h for kw in ["china", "tariff", "trade war", "sanctions", "geopolitical"]):
            return NewsCategory.GEOPOLITICAL
        if any(kw in h for kw in ["gdp", "inflation", "unemployment", "pmi", "economy"]):
            return NewsCategory.MACRO
        if any(kw in h for kw in ["asic", "regulation", "government", "policy", "legislation"]):
            return NewsCategory.REGULATORY
        if any(kw in h for kw in ["fed", "us market", "wall street", "nasdaq", "s&p"]):
            return NewsCategory.GLOBAL

        return NewsCategory.SECTOR

    def _score_relevance(self, items: List[NewsItem]) -> List[NewsItem]:
        """Score items by Australian market relevance."""
        now = datetime.now(timezone.utc)

        for item in items:
            score = item.relevance_score
            text = f"{item.headline} {item.summary}".lower()

            au_matches = sum(1 for kw in self.HIGH_RELEVANCE_KEYWORDS if kw.lower() in text)
            score += au_matches * 0.1

            if item.tickers:
                score += len(item.tickers) * 0.05

            age_hours = (now - item.published_at).total_seconds() / 3600
            if age_hours < 6:
                score += 0.2
            elif age_hours < 12:
                score += 0.1

            item.relevance_score = min(1.0, score)

        return items

    def _deduplicate(self, items: List[NewsItem]) -> List[NewsItem]:
        """Remove duplicate headlines."""
        seen: Set[str] = set()
        unique: List[NewsItem] = []

        for item in items:
            key = item.headline.lower().strip()[:50]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique


# Module-level singleton
_aggregator: Optional[ASXNewsAggregator] = None


def get_aggregator() -> ASXNewsAggregator:
    """Get or create the global aggregator instance."""
    global _aggregator

    if _aggregator is None:
        import os
        _aggregator = ASXNewsAggregator(
            marketaux_api_key=os.getenv("MARKETAUX_API_KEY"),
            alphavantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY"),
        )

    return _aggregator


async def fetch_asx_news(
    hours: int = 24,
    min_items: int = 20,
    max_items: int = 50,
) -> Dict[str, Any]:
    """
    Convenience function to fetch ASX news.

    Returns dict with news items grouped by category.
    """
    aggregator = get_aggregator()
    result = await aggregator.fetch_all_news(
        hours=hours,
        min_items=min_items,
        max_items=max_items,
    )
    return result.to_dict()
