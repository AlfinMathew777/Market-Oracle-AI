"""
Morning Pre-Market Prediction Runner
=====================================
Runs a simulation for each watched ticker before ASX opens.
Saves results to prediction_log via the existing /api/simulate pipeline.

Railway cron schedule: "30 23 * * 0-4"
  = 23:30 UTC Sun–Thu = 09:30 AEST Mon–Fri (UTC+10)

Usage:
  python3 backend/scripts/morning_prediction.py           # all tickers
  python3 backend/scripts/morning_prediction.py BHP.AX   # single ticker

Environment variables (all optional with sensible defaults):
  BACKEND_URL         - defaults to http://localhost:8000
  MORNING_TICKERS     - comma-separated override, e.g. "BHP.AX,CBA.AX,WDS.AX"
  API_KEY             - if backend requires it (matches server API_KEY env var)
  DRY_RUN             - set to "1" to print payload without calling the API
"""

import asyncio
import httpx
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("morning_prediction")

# ── Configuration ─────────────────────────────────────────────────────────────

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")

# Default watchlist — override via MORNING_TICKERS env var or CLI arg
_DEFAULT_TICKERS = [
    "BHP.AX",   # iron ore bellwether, most liquid ASX resource
    "RIO.AX",   # diversified miner, iron ore + copper
    "FMG.AX",   # pure-play Pilbara iron ore, China-sensitive
    "WDS.AX",   # largest ASX LNG exporter, Suez/Malacca exposed
    "STO.AX",   # Santos — Darwin LNG, Asia-Pacific routes
    "CBA.AX",   # big-4 bank, macro/RBA rate proxy
]

_TICKER_CONTEXTS = {
    "BHP.AX":  ("Iron ore price movement and China steel demand signals",      "china_trade",  -33.9, 151.2, "Australia"),
    "RIO.AX":  ("Iron ore and copper market dynamics ahead of ASX open",       "china_trade",  -33.9, 151.2, "Australia"),
    "FMG.AX":  ("Pilbara iron ore export volumes and China spot price",        "china_trade",  -22.3, 118.6, "Australia"),
    "WDS.AX":  ("LNG spot price and European energy demand signals",           "middle_east",   -32.0,  115.9, "Australia"),
    "STO.AX":  ("Asia-Pacific LNG demand and Darwin export terminal update",   "asean_trade",  -12.5, 130.8, "Australia"),
    "CBA.AX":  ("RBA rate outlook and Australian domestic economic conditions","australia_domestic", -33.9, 151.2, "Australia"),
}

_DEFAULT_CONTEXT = (
    "Pre-market geopolitical and commodity scan for ASX open",
    "australia_domestic", -33.9, 151.2, "Australia",
)

API_KEY = os.environ.get("API_KEY", "")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"

# Timeout per simulation — the 50-agent pipeline takes 2–4 min on Railway
SIMULATION_TIMEOUT_SECS = 360

# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_event(ticker: str) -> dict:
    """Construct a synthetic pre-market event for the given ticker."""
    description, region, lat, lon, country = _TICKER_CONTEXTS.get(ticker, _DEFAULT_CONTEXT)
    aest_now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "event_id":          f"premarket_{aest_now}_{ticker.replace('.', '_')}",
        "event_description": f"Pre-market scan: {description}. Date: {aest_now}.",
        "event_type":        "Strategic developments",
        "lat":               lat,
        "lon":               lon,
        "country":           country,
        "fatalities":        0,
        "affected_tickers":  [ticker],
        "date":              aest_now,
    }


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


# ── Core runner ───────────────────────────────────────────────────────────────

async def simulate_ticker(client: httpx.AsyncClient, ticker: str) -> dict | None:
    """Run one simulation for a ticker. Returns prediction dict or None on failure."""
    payload = _build_event(ticker)

    if DRY_RUN:
        logger.info("[DRY RUN] Would POST /api/simulate: %s", payload)
        return None

    logger.info("Starting simulation: %s", ticker)
    try:
        resp = await client.post(
            f"{BACKEND_URL}/api/simulate",
            json=payload,
            headers=_headers(),
            timeout=SIMULATION_TIMEOUT_SECS,
        )
        resp.raise_for_status()
        result = resp.json()

        if result.get("status") != "completed" or not result.get("prediction"):
            logger.warning("Simulation returned non-completed status for %s: %s", ticker, result.get("status"))
            return None

        pred = result["prediction"]
        direction  = pred.get("direction", "NEUTRAL")
        confidence = pred.get("confidence", 0)
        conf_pct   = round(confidence * 100 if confidence <= 1 else confidence, 1)

        logger.info(
            "✅  %s  →  %-7s  %.1f%%  (sim_id: %s)",
            ticker, direction, conf_pct, result.get("simulation_id", "?"),
        )
        # _persist_simulation() inside /api/simulate already saved to prediction_log —
        # no second POST needed. Just return the result for the summary.
        return {"ticker": ticker, "direction": direction, "confidence": conf_pct, "prediction": pred}

    except httpx.TimeoutException:
        logger.error("❌  %s  timed out after %ds", ticker, SIMULATION_TIMEOUT_SECS)
    except httpx.HTTPStatusError as e:
        logger.error("❌  %s  HTTP %d: %s", ticker, e.response.status_code, e.response.text[:200])
    except Exception as e:
        logger.error("❌  %s  unexpected error: %s", ticker, e, exc_info=True)
    return None


async def run_morning_predictions(tickers: list[str]) -> None:
    aest_label = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logger.info("=" * 60)
    logger.info("Morning Pre-Market Run  |  %s", aest_label)
    logger.info("Backend: %s  |  Tickers: %s", BACKEND_URL, ", ".join(tickers))
    logger.info("=" * 60)

    results = []
    # Run sequentially — the 50-agent simulation is already parallel internally.
    # Concurrent outer calls would hammer the LLM rate limits.
    async with httpx.AsyncClient() as client:
        for ticker in tickers:
            result = await simulate_ticker(client, ticker)
            if result:
                results.append(result)
            # Brief pause between tickers to avoid rate-limit burst
            await asyncio.sleep(3)

    # ── Summary ──────────────────────────────────────────────────────────────
    logger.info("-" * 60)
    logger.info("SUMMARY  %d/%d tickers completed", len(results), len(tickers))
    for r in results:
        arrow = "▲" if r["direction"] == "UP" else "▼" if r["direction"] == "DOWN" else "—"
        logger.info("  %s  %s  %.1f%%", r["ticker"], arrow, r["confidence"])
    if len(results) < len(tickers):
        failed = [t for t in tickers if not any(r["ticker"] == t for r in results)]
        logger.warning("  Failed: %s", ", ".join(failed))
    logger.info("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    # CLI arg: single ticker override
    if len(sys.argv) > 1:
        tickers = [t.upper() for t in sys.argv[1:]]
    # Env var: comma-separated list
    elif os.environ.get("MORNING_TICKERS"):
        tickers = [t.strip().upper() for t in os.environ["MORNING_TICKERS"].split(",") if t.strip()]
    else:
        tickers = _DEFAULT_TICKERS

    asyncio.run(run_morning_predictions(tickers))


if __name__ == "__main__":
    main()
