"""Chokepoint Monitor Service ? live data enrichment from free sources.

Sources:
1. NGA Maritime Safety (US Navy) ? navigational warnings, no key required
2. GDELT tone analysis per chokepoint ? no key required
3. FRED Baltic Dry Index ? uses existing FRED key
4. ACLED proximity filter ? uses existing ACLED key when available
"""

import requests
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict

logger = logging.getLogger(__name__)

# NGA NAVTEX regions mapped to chokepoints
NGA_REGIONS = {
    "hormuz":       "https://msi.nga.mil/api/publications/query?type=NAVTEX&output=json&status=active&navArea=IX",
    "malacca":      "https://msi.nga.mil/api/publications/query?type=NAVTEX&output=json&status=active&navArea=XI",
    "suez":         "https://msi.nga.mil/api/publications/query?type=NAVTEX&output=json&status=active&navArea=V",
    "bab_el_mandeb":"https://msi.nga.mil/api/publications/query?type=NAVTEX&output=json&status=active&navArea=IX",
    "cape_good_hope":"https://msi.nga.mil/api/publications/query?type=NAVTEX&output=json&status=active&navArea=VI",
    "lombok":       "https://msi.nga.mil/api/publications/query?type=NAVTEX&output=json&status=active&navArea=XI",
}

CHOKEPOINT_GDELT_QUERIES = {
    "hormuz":       "Strait of Hormuz shipping tanker Iran",
    "malacca":      "Strait of Malacca shipping piracy China",
    "bab_el_mandeb":"Bab el-Mandeb Houthi Red Sea shipping",
    "suez":         "Suez Canal shipping blockage Egypt",
    "cape_good_hope":"Cape of Good Hope shipping reroute",
    "lombok":       "Lombok Strait Indonesia shipping iron ore",
    "panama":       "Panama Canal drought water level shipping",
    "turkish_straits":"Bosphorus Turkey Russia oil shipping",
    "danish_straits":"Baltic Sea NATO Russia shipping",
}

# 4-hour cache for NGA warnings
_nga_cache: Dict = {}
_nga_cache_expiry: datetime | None = None

# 1-hour cache for GDELT per-chokepoint
_gdelt_cache: Dict = {}
_gdelt_cache_expiry: datetime | None = None


def get_nga_navigational_warnings() -> Dict:
    """Fetch US Navy navigational warnings for chokepoint regions. No API key needed."""
    global _nga_cache, _nga_cache_expiry

    now = datetime.now(timezone.utc)
    if _nga_cache and _nga_cache_expiry and now < _nga_cache_expiry:
        return _nga_cache

    results = {}
    for region_name, url in NGA_REGIONS.items():
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                warnings = r.json().get("pubs", [])
                results[region_name] = {
                    "warning_count": len(warnings),
                    "warnings": [w.get("title", "") for w in warnings[:5]],
                    "risk_signal": "HIGH" if len(warnings) > 5 else "MEDIUM" if len(warnings) > 2 else "LOW",
                }
            else:
                results[region_name] = {"warning_count": 0, "warnings": [], "risk_signal": "UNKNOWN"}
        except Exception as e:
            logger.warning(f"NGA warning fetch failed for {region_name}: {e}")
            results[region_name] = {"warning_count": 0, "warnings": [], "risk_signal": "UNAVAILABLE"}

    _nga_cache = results
    _nga_cache_expiry = now + timedelta(hours=4)
    return results


def get_gdelt_chokepoint_sentiment() -> Dict:
    """Get GDELT tone score for each chokepoint query. No API key needed."""
    global _gdelt_cache, _gdelt_cache_expiry

    now = datetime.now(timezone.utc)
    if _gdelt_cache and _gdelt_cache_expiry and now < _gdelt_cache_expiry:
        return _gdelt_cache

    try:
        from services.gdelt_service import get_gdelt_sentiment_score
    except ImportError:
        logger.warning("gdelt_service not available")
        return {}

    results = {}
    for cp_id, query in CHOKEPOINT_GDELT_QUERIES.items():
        try:
            data = get_gdelt_sentiment_score(query, max_records=20)
            results[cp_id] = {
                "tone": data.get("avgtone", 0),
                "article_count": data.get("article_count", 0),
                "sentiment": data.get("sentiment", "NEUTRAL"),
                "risk_signal": "HIGH" if data.get("avgtone", 0) < -3 else "MEDIUM" if data.get("avgtone", 0) < -1 else "LOW",
            }
        except Exception as e:
            logger.warning(f"GDELT fetch failed for {cp_id}: {e}")
            results[cp_id] = {"tone": 0, "article_count": 0, "sentiment": "UNAVAILABLE", "risk_signal": "UNKNOWN"}

    _gdelt_cache = results
    _gdelt_cache_expiry = now + timedelta(hours=1)
    return results


def get_baltic_dry_index() -> Dict:
    """Fetch Baltic Dry Index from FRED ? direct chokepoint disruption signal."""
    fred_key = os.getenv("FRED_API_KEY")
    if not fred_key:
        return {"status": "pending_api_key", "value": None, "signal": "UNKNOWN"}

    try:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id=BDRIY&api_key={fred_key}&sort_order=desc&limit=1&file_type=json"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        if obs and obs[0].get("value") != ".":
            value = float(obs[0]["value"])
            # BDI > 2000 = high demand/constrained supply, < 1000 = weak
            signal = "HIGH_DEMAND" if value > 2000 else "ELEVATED" if value > 1500 else "NORMAL" if value > 1000 else "WEAK"
            return {
                "status": "ok",
                "value": value,
                "date": obs[0].get("date"),
                "signal": signal,
                "interpretation": f"BDI {value:.0f} ? {'shipping demand high, possible chokepoint constraint' if value > 1500 else 'normal shipping conditions'}",
            }
    except Exception as e:
        logger.warning(f"Baltic Dry Index fetch failed: {e}")

    return {"status": "error", "value": None, "signal": "UNKNOWN"}


_enriched_cache: Dict = {}
_enriched_cache_expiry: datetime | None = None


def get_enriched_chokepoint_risks() -> Dict:
    """
    Combine base risk scores with live NGA warnings and GDELT sentiment.
    Cached for 15 minutes ? enrichment calls are expensive.
    """
    global _enriched_cache, _enriched_cache_expiry
    now = datetime.now(timezone.utc)
    if _enriched_cache and _enriched_cache_expiry and now < _enriched_cache_expiry:
        logger.info("Returning cached enriched chokepoint risks")
        return _enriched_cache
    from services.chokepoint_service import get_all_chokepoint_risks

    base = get_all_chokepoint_risks()
    nga_warnings = get_nga_navigational_warnings()
    gdelt_sentiment = get_gdelt_chokepoint_sentiment()
    bdi = get_baltic_dry_index()

    # Enrich each chokepoint
    for cp_id, cp_data in base["chokepoints"].items():
        nga = nga_warnings.get(cp_id, {})
        gdelt = gdelt_sentiment.get(cp_id, {})

        # Bump risk score if NGA warnings are elevated
        if nga.get("risk_signal") == "HIGH":
            cp_data["risk_score"] = min(cp_data["risk_score"] + 10, 100)
            cp_data["nga_warnings"] = nga.get("warnings", [])
            cp_data["nga_warning_count"] = nga.get("warning_count", 0)

        # Bump risk score if GDELT sentiment is very negative
        if gdelt.get("risk_signal") == "HIGH":
            cp_data["risk_score"] = min(cp_data["risk_score"] + 8, 100)
        cp_data["gdelt_tone"] = gdelt.get("tone", 0)
        cp_data["gdelt_articles"] = gdelt.get("article_count", 0)

        # Recompute color after enrichment
        score = cp_data["risk_score"]
        cp_data["color"] = (
            "#ff2222" if score > 70 else
            "#ff8800" if score > 45 else
            "#ffcc00" if score > 25 else
            "#44ff88"
        )

    base["baltic_dry_index"] = bdi
    base["data_sources"] = ["chokepoint_service", "nga_maritime", "gdelt", "fred_bdi"]

    _enriched_cache = base
    _enriched_cache_expiry = now + timedelta(minutes=15)
    return base


# Real EIA 2025 H1 flow data (official, updated semi-annually)
EIA_FLOWS_2025_H1 = {
    "malacca":       {"mbd": 23.2, "pct_maritime": 29.1},
    "hormuz":        {"mbd": 20.9, "pct_maritime": 25.0},
    "cape_good_hope":{"mbd": 9.1,  "pct_maritime": 11.4},
    "suez":          {"mbd": 4.9,  "pct_maritime": 6.1},
    "bab_el_mandeb": {"mbd": 4.2,  "pct_maritime": 5.3},
    "panama":        {"mbd": 3.8,  "pct_maritime": 4.8},
    "danish_straits":{"mbd": 3.0,  "pct_maritime": 3.8},
    "turkish_straits":{"mbd": 2.9, "pct_maritime": 3.6},
    "lombok":        {"mbd": 1.5,  "pct_maritime": 1.9},
}
