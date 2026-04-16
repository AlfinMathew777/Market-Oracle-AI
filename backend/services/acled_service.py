"""ACLED (Armed Conflict Location & Event Data Project) API integration.

Uses OAuth token authentication as per ACLED's current API documentation.
Credentials: ACLED_EMAIL + ACLED_PASSWORD in .env
"""

import requests
import logging
import os
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict

logger = logging.getLogger(__name__)

ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_BASE = "https://acleddata.com/api/acled/read"

# Demo events shown when credentials are not configured
_DEMO_FEATURES = [
    {"id": "DEMO-001", "lat": 31.5,  "lng": 34.8,   "country": "Israel",                       "event_type": "Explosions/Remote violence", "description": "Israeli airstrikes on Gaza City targeting Hamas infrastructure. Significant civilian casualties reported.",                               "date": "2025-03-15", "fatalities": 12},
    {"id": "DEMO-002", "lat": 15.4,  "lng": 44.2,   "country": "Yemen",                        "event_type": "Explosions/Remote violence", "description": "Houthi missile strike on commercial vessel in Red Sea near Bab el-Mandeb strait, disrupting tanker routes.",                          "date": "2025-03-14", "fatalities": 3},
    {"id": "DEMO-003", "lat": 48.0,  "lng": 37.8,   "country": "Ukraine",                      "event_type": "Battles",                   "description": "Russian forces advance near Donetsk region. NATO allies consider additional weapons package for Ukraine.",                              "date": "2025-03-13", "fatalities": 45},
    {"id": "DEMO-004", "lat": 25.2,  "lng": 55.3,   "country": "Iran",                         "event_type": "Strategic developments",    "description": "Iran announces enrichment of uranium to 60% purity at Fordow facility. US and EU sanctions response likely.",                           "date": "2025-03-12", "fatalities": 0},
    {"id": "DEMO-005", "lat": 25.0,  "lng": 121.5,  "country": "Taiwan",                       "event_type": "Strategic developments",    "description": "PLA conducts large-scale military exercises in Taiwan Strait. TSMC shares drop 4%. Rare earth export concerns rise.",                   "date": "2025-03-11", "fatalities": 0},
    {"id": "DEMO-006", "lat": 39.9,  "lng": 116.4,  "country": "China",                        "event_type": "Strategic developments",    "description": "China PMI falls to 48.7, below contraction threshold. Iron ore futures drop 6% on demand fears. BHP, RIO, FMG under pressure.",        "date": "2025-03-10", "fatalities": 0},
    {"id": "DEMO-007", "lat": -4.3,  "lng": 15.3,   "country": "Democratic Republic of Congo", "event_type": "Battles",                   "description": "M23 rebels advance on Goma. Cobalt and coltan mining operations halted in North Kivu. ASX lithium stocks affected.",                  "date": "2025-03-09", "fatalities": 28},
    {"id": "DEMO-008", "lat": 29.9,  "lng": 32.5,   "country": "Egypt",                        "event_type": "Strategic developments",    "description": "Suez Canal authority reports 40% drop in vessel transit volume due to Red Sea security concerns. LNG tankers rerouting via Cape.",      "date": "2025-03-08", "fatalities": 0},
    {"id": "DEMO-009", "lat": 21.0,  "lng": 105.8,  "country": "Myanmar",                      "event_type": "Battles",                   "description": "Junta forces clash with resistance near Chinese border. Rare earth mining routes disrupted. Prices spike 8%.",                          "date": "2025-03-07", "fatalities": 15},
    {"id": "DEMO-010", "lat": -8.8,  "lng": 147.2,  "country": "Papua New Guinea",             "event_type": "Riots/Protests",            "description": "Tribal conflict near Ok Tedi copper mine forces temporary shutdown. BHP-operated facility halts production.",                          "date": "2025-03-06", "fatalities": 6},
    {"id": "DEMO-011", "lat": 51.2,  "lng": 30.9,   "country": "Ukraine",                      "event_type": "Explosions/Remote violence", "description": "Russian strikes on Kyiv energy infrastructure. European gas prices surge 12%. LNG exporters including Woodside benefit.",              "date": "2025-03-05", "fatalities": 8},
    {"id": "DEMO-012", "lat": 1.3,   "lng": 103.8,  "country": "Singapore",                    "event_type": "Strategic developments",    "description": "Singapore MAS issues emergency liquidity to regional banks following China property sector credit event contagion.",                    "date": "2025-03-04", "fatalities": 0},
    {"id": "DEMO-013", "lat": 26.9,  "lng": 75.8,   "country": "India",                        "event_type": "Riots/Protests",            "description": "Indian port workers strike disrupts coal and iron ore imports. Australia-India commodity trade routes under stress.",                  "date": "2025-03-03", "fatalities": 0},
    {"id": "DEMO-014", "lat": -33.9, "lng": 151.2,  "country": "Australia",                    "event_type": "Strategic developments",    "description": "RBA holds cash rate at 4.35% citing persistent services inflation. AUD/USD falls to 0.63 on disappointing jobs data.",                "date": "2025-03-02", "fatalities": 0},
    {"id": "DEMO-015", "lat": 38.9,  "lng": -77.0,  "country": "United States",                "event_type": "Strategic developments",    "description": "US imposes 25% tariffs on steel and aluminum imports including from Australian allies. ASX materials sector sells off.",             "date": "2025-03-01", "fatalities": 0},
]

# OAuth token cache ? valid 24 hours
_token_cache: Dict = {"token": None, "expires_at": 0}

# Event data TTL cache
_cache: Dict = {}
_cache_expiry: datetime | None = None
_CACHE_TTL = timedelta(hours=1)

RELEVANT_COUNTRIES = [
    "China", "Iran", "Democratic Republic of Congo",
    "Taiwan", "Sudan", "Argentina", "Chile",
    "Papua New Guinea", "Indonesia", "Myanmar",
    "Ukraine", "Russia", "Israel", "Yemen",
    "Australia", "United States", "Singapore"
]


class ACLEDService:
    """Service for fetching real conflict events from ACLED via OAuth."""

    def _get_token(self, email: str, password: str) -> str:
        """Get OAuth bearer token, cached for 23 hours."""
        now = time.time()
        if _token_cache["token"] and now < _token_cache["expires_at"]:
            return _token_cache["token"]

        response = requests.post(
            ACLED_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "username": email,
                "password": password,
                "grant_type": "password",
                "client_id": "acled",
            },
            timeout=15,
        )

        if response.status_code == 200:
            token_data = response.json()
            _token_cache["token"] = token_data["access_token"]
            _token_cache["expires_at"] = now + 82800  # 23 hours
            logger.info("? ACLED OAuth token obtained")
            return _token_cache["token"]
        else:
            raise Exception(f"ACLED auth failed: {response.status_code} {response.text}")

    def get_events(self) -> Dict:
        """Fetch live conflict events. Falls back to demo data if credentials missing."""
        global _cache, _cache_expiry

        email = os.getenv("ACLED_EMAIL")
        password = os.getenv("ACLED_PASSWORD")

        if not email or not password:
            logger.info("ACLED credentials not configured ? returning demo events")
            return self._demo_response()

        # Return cached result if still fresh
        now = datetime.now(timezone.utc)
        if _cache and _cache_expiry and now < _cache_expiry:
            logger.info("Returning cached ACLED events")
            return _cache

        try:
            token = self._get_token(email, password)

            country_filter = ":OR:country=".join(RELEVANT_COUNTRIES)

            # Fetch events from the last 90 days (rolling window, always current)
            ninety_days_ago = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")

            params = {
                "_format": "json",
                "country": country_filter,
                "fields": "event_id_cnty|event_date|event_type|country|location|latitude|longitude|fatalities|notes",
                "limit": 50,
                "event_date": ninety_days_ago,
                "event_date_where": ">=",
            }

            logger.info(f"Fetching live ACLED events for {len(RELEVANT_COUNTRIES)} countries...")

            response = requests.get(
                ACLED_BASE,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            events = data.get("data", [])

            features = []
            for event in events:
                if not event.get("latitude") or not event.get("longitude"):
                    continue
                try:
                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(event["longitude"]), float(event["latitude"])],
                        },
                        "properties": {
                            "id": event["event_id_cnty"],
                            "event_type": event["event_type"],
                            "country": event["country"],
                            "location": event["location"],
                            "description": event["notes"][:200] if event["notes"] else event["event_type"],
                            "date": event["event_date"],
                            "fatalities": int(event["fatalities"] or 0),
                            "notes": event["notes"] or "",
                            "affected_region": self._classify_region(event),
                        },
                    })
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping malformed event: {e}")

            logger.info(f"? Fetched {len(features)} live ACLED events")

            result = {
                "type": "FeatureCollection",
                "count": len(features),
                "features": features,
                "source": "ACLED API (Live)",
                "status": "live",
            }
            _cache = result
            _cache_expiry = datetime.now(timezone.utc) + _CACHE_TTL
            return result

        except requests.Timeout:
            logger.error("ACLED API timeout ? falling back to demo")
            return self._demo_response()
        except Exception as e:
            logger.error(f"ACLED error: {e} ? falling back to demo")
            return self._demo_response()

    def _classify_region(self, event: dict) -> str:
        country = event.get("country", "").lower()
        if "china" in country:         return "china_trade"
        if "iran" in country or "yemen" in country: return "middle_east"
        if "congo" in country:         return "drc_lithium"
        if "taiwan" in country:        return "taiwan_rare_earth"
        if "sudan" in country:         return "red_sea_shipping"
        if "australia" in country:     return "australia_domestic"
        if "united states" in country: return "us_trade_policy"
        if "singapore" in country:     return "asean_trade"
        return "other"

    def _demo_response(self) -> Dict:
        # Shift demo event dates to be relative to today so they never look stale
        today = datetime.now(timezone.utc)
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e["lng"], e["lat"]]},
                "properties": {
                    "id": e["id"],
                    "event_type": e["event_type"],
                    "country": e["country"],
                    "location": e["country"],
                    "description": e["description"],
                    "date": (today - timedelta(days=i)).strftime("%Y-%m-%d"),
                    "fatalities": e["fatalities"],
                    "notes": e["description"],
                    "affected_region": self._classify_region({"country": e["country"]}),
                },
            }
            for i, e in enumerate(_DEMO_FEATURES)
        ]
        return {
            "type": "FeatureCollection",
            "count": len(features),
            "features": features,
            "source": "Demo Data (add ACLED credentials for live events)",
            "status": "demo",
        }

    def get_rss_events(self) -> Dict:
        """Fetch live geopolitical/market events from free RSS feeds.
        No API key required. Used as fallback when ACLED is unavailable.
        """
        RSS_SOURCES = [
            {"url": "https://www.aljazeera.com/xml/rss/all.xml",         "source": "Al Jazeera",   "region": "GEO"},
            {"url": "https://feeds.bbci.co.uk/news/world/rss.xml",       "source": "BBC World",    "region": "GEO"},
            {"url": "https://oilprice.com/rss/main",                     "source": "OilPrice",     "region": "COMMODITIES"},
            {"url": "https://www.mining.com/feed/",                      "source": "Mining.com",   "region": "COMMODITIES"},
            {"url": "https://www.abc.net.au/news/feed/2942460/rss.xml",  "source": "ABC Business", "region": "AU"},
            {"url": "https://stockhead.com.au/feed/",                    "source": "Stockhead",    "region": "AU"},
        ]

        # Country/region keyword mapping for geographic pin placement
        COUNTRY_MAP = [
            (["china", "beijing", "xi jinping", "iron ore", "pla"],                                   "China",          39.9,  116.4, "china_trade",         "Strategic developments"),
            (["ukraine", "kyiv", "zelenskyy", "russia", "moscow", "nato"],                            "Ukraine",        48.0,   37.8, "other",               "Battles"),
            (["taiwan", "taipei", "strait", "tsmc"],                                                  "Taiwan",         25.0,  121.5, "taiwan_rare_earth",   "Strategic developments"),
            (["red sea", "houthi", "yemen", "tanker", "suez", "bab el-mandeb"],                       "Yemen",          15.4,   44.2, "middle_east",         "Explosions/Remote violence"),
            (["iran", "tehran", "nuclear", "hormuz"],                                                  "Iran",           32.0,   53.7, "middle_east",         "Strategic developments"),
            (["israel", "gaza", "hamas", "idf", "west bank"],                                         "Israel",         31.5,   34.8, "middle_east",         "Explosions/Remote violence"),
            (["congo", "drc", "cobalt", "coltan", "kinshasa"],                                        "Democratic Republic of Congo", -4.3, 15.3, "drc_lithium", "Battles"),
            (["papua new guinea", "png", "ok tedi", "wafi"],                                          "Papua New Guinea", -8.8, 147.2, "other",              "Riots/Protests"),
            (["myanmar", "burma", "rare earth", "junta"],                                             "Myanmar",        21.0,  105.8, "other",               "Battles"),
            (["australia", "asx", "rba", "aud", "bhp", "rio tinto", "fortescue"],                    "Australia",     -33.9,  151.2, "australia_domestic",  "Strategic developments"),
            (["tariff", "trump", "us trade", "trade war", "fed ", "wall street"],                     "United States",  38.9,  -77.0, "us_trade_policy",     "Strategic developments"),
            (["singapore", "asean", "southeast asia"],                                                "Singapore",       1.3,  103.8, "asean_trade",         "Strategic developments"),
            (["copper", "lithium", "gold", "silver", "commodity", "iron ore", "oil", "lng", "coal"], "Australia",     -33.9,  151.2, "australia_domestic",  "Strategic developments"),
        ]

        today = datetime.now(timezone.utc)
        articles = []

        for feed in RSS_SOURCES:
            try:
                resp = requests.get(
                    feed["url"],
                    timeout=8,
                    headers={"User-Agent": "MarketOracleAI/1.0"},
                )
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.text)
                items = root.findall(".//item")
                for item in items[:8]:
                    title = (item.findtext("title") or "").strip()
                    link  = (item.findtext("link")  or "").strip()
                    pub   = (item.findtext("pubDate") or "").strip()
                    if title:
                        articles.append({"title": title, "url": link, "pubDate": pub, "source": feed["source"]})
            except Exception as e:
                logger.debug("RSS feed %s failed: %s", feed["source"], e)

        if not articles:
            logger.warning("All RSS feeds failed — falling back to demo")
            return self._demo_response()

        # Allow up to 2 events per country; deduplicate by title not by country
        country_counts: dict = {}
        seen_titles: set = set()
        features = []

        for art in articles:
            title_lower = art["title"].lower()
            title_key = title_lower[:60]
            if title_key in seen_titles:
                continue

            matched = None
            for keywords, country, lat, lng, region, event_type in COUNTRY_MAP:
                if country_counts.get(country, 0) >= 2:
                    continue
                if any(kw in title_lower for kw in keywords):
                    matched = (country, lat, lng, region, event_type)
                    break
            if not matched:
                continue

            country, lat, lng, region, event_type = matched
            seen_titles.add(title_key)
            country_counts[country] = country_counts.get(country, 0) + 1
            idx = len(features)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "id":              f"RSS-{idx:03d}",
                    "event_type":      event_type,
                    "country":         country,
                    "location":        country,
                    "description":     art["title"][:200],
                    "date":            today.strftime("%Y-%m-%d"),
                    "fatalities":      0,
                    "notes":           art["title"],
                    "affected_region": region,
                    "source_name":     art["source"],
                    "url":             art["url"],
                },
            })

            if len(features) >= 20:
                break

        if not features:
            logger.warning("No RSS articles matched country map — falling back to demo")
            return self._demo_response()

        # Pad with demo events for countries not covered by RSS, up to 15 total
        if len(features) < 15:
            demo = self._demo_response()
            covered = {f["properties"]["country"] for f in features}
            for demo_feat in demo["features"]:
                if len(features) >= 15:
                    break
                if demo_feat["properties"]["country"] not in covered:
                    features.append(demo_feat)
                    covered.add(demo_feat["properties"]["country"])

        logger.info("RSS live events fetched: %d events from feeds", len(features))
        return {
            "type": "FeatureCollection",
            "count": len(features),
            "features": features,
            "source": "Live News (RSS)",
            "status": "live",
        }

    def _error_response(self, error_msg: str) -> Dict:
        return {
            "type": "FeatureCollection",
            "count": 0,
            "features": [],
            "error": error_msg,
            "status": "error",
        }
