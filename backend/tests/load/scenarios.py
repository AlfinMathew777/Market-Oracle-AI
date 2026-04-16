"""Reusable load test scenarios for Market Oracle AI.

Each scenario is a callable that performs one logical user action.
Imported by locustfile.py and composed into user classes.

Scenarios:
  health_check()          — GET /api/health (baseline, no auth)
  fetch_prediction_history()  — GET /api/data/prediction-history
  fetch_acled_events()    — GET /api/data/acled
  fetch_asx_prices()      — GET /api/data/asx-prices
  fetch_chokepoint_risks()    — GET /api/data/chokepoints
  simulate_event()        — POST /api/simulate (heaviest: triggers LLM)
  fetch_accuracy_stats()  — GET /api/quant/accuracy
"""

import random

# ── Sample event payloads for simulate_event ─────────────────────────────────

_SAMPLE_EVENTS = [
    {
        "event_type": "Battles",
        "country": "Myanmar",
        "location": "Yangon",
        "notes": "Military clashes near Yangon port causing supply disruption",
        "ticker": "BHP.AX",
    },
    {
        "event_type": "Violence against civilians",
        "country": "Sudan",
        "location": "Port Sudan",
        "notes": "Unrest near Port Sudan — Red Sea shipping route at risk",
        "ticker": "WDS.AX",
    },
    {
        "event_type": "Protests",
        "country": "Indonesia",
        "location": "Lombok",
        "notes": "Dock worker strikes at Lembar Port disrupting iron ore transit",
        "ticker": "RIO.AX",
    },
    {
        "event_type": "Strategic developments",
        "country": "China",
        "location": "Beijing",
        "notes": "China announces new steel production quotas affecting iron ore demand",
        "ticker": "FMG.AX",
    },
    {
        "event_type": "Explosions/Remote violence",
        "country": "Yemen",
        "location": "Bab-el-Mandeb",
        "notes": "Houthi attack on cargo vessel in Red Sea shipping lane",
        "ticker": "STO.AX",
    },
]

_TICKERS = ["BHP.AX", "RIO.AX", "FMG.AX", "WDS.AX", "STO.AX", "CBA.AX", "ANZ.AX"]


def health_check(client):
    """Lightweight connectivity probe — no auth."""
    with client.get("/api/health", name="/api/health", catch_response=True) as resp:
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") != "operational":
                resp.failure(f"Unexpected status: {data.get('status')}")
        else:
            resp.failure(f"HTTP {resp.status_code}")


def fetch_prediction_history(client):
    """GET prediction history — tests SQLite/PG read path."""
    ticker = random.choice(_TICKERS)
    with client.get(
        f"/api/data/prediction-history?ticker={ticker}&limit=20",
        name="/api/data/prediction-history",
        catch_response=True,
    ) as resp:
        if resp.status_code not in (200, 404):
            resp.failure(f"HTTP {resp.status_code}")


def fetch_acled_events(client):
    """GET conflict events — tests Redis cache + ACLED service."""
    with client.get(
        "/api/data/acled",
        name="/api/data/acled",
        catch_response=True,
    ) as resp:
        if resp.status_code not in (200, 503):
            resp.failure(f"HTTP {resp.status_code}")


def fetch_asx_prices(client):
    """GET ASX prices — tests yfinance + Redis price cache."""
    with client.get(
        "/api/data/asx-prices",
        name="/api/data/asx-prices",
        catch_response=True,
    ) as resp:
        if resp.status_code not in (200, 503):
            resp.failure(f"HTTP {resp.status_code}")


def fetch_chokepoint_risks(client):
    """GET chokepoint risk scores — tests chokepoint service."""
    with client.get(
        "/api/data/chokepoints",
        name="/api/data/chokepoints",
        catch_response=True,
    ) as resp:
        if resp.status_code not in (200, 404):
            resp.failure(f"HTTP {resp.status_code}")


def simulate_event(client, api_key: str = ""):
    """POST a simulation — heaviest endpoint, triggers 45-agent LLM pipeline."""
    event = random.choice(_SAMPLE_EVENTS)
    headers = {"X-API-Key": api_key} if api_key else {}
    with client.post(
        "/api/simulate",
        json=event,
        headers=headers,
        name="/api/simulate",
        catch_response=True,
        timeout=120,  # simulation can take up to 2 minutes
    ) as resp:
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") not in ("success", "pending"):
                resp.failure(f"Unexpected sim status: {data.get('status')}")
        elif resp.status_code == 429:
            resp.success()  # rate-limited is expected under load
        elif resp.status_code in (401, 403):
            resp.success()  # auth failure expected without key in load tests
        else:
            resp.failure(f"HTTP {resp.status_code}")


def fetch_accuracy_stats(client):
    """GET accuracy statistics — tests prediction_log aggregate queries."""
    with client.get(
        "/api/quant/accuracy",
        name="/api/quant/accuracy",
        catch_response=True,
    ) as resp:
        if resp.status_code not in (200, 404):
            resp.failure(f"HTTP {resp.status_code}")
