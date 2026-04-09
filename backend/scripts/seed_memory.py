"""
Seed Memory Script
------------------
Runs 6 reasoning predictions for BHP.AX to build enough history for
PredictionMemory to activate confidence calibration.

Usage:
    cd backend
    python scripts/seed_memory.py

Requires:
    - Backend running on localhost:8000 (or set BACKEND_URL env var)
    - MARKET_ORACLE_API_KEYS set (or REACT_APP_API_KEY for dev)
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
import urllib.error

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
API_KEY = os.environ.get("MARKET_ORACLE_API_KEY", os.environ.get("REACT_APP_API_KEY", ""))

SCENARIOS = [
    {
        "label": "Strong China stimulus (BUY)",
        "agent_votes": {"bullish": 35, "bearish": 3, "neutral": 7},
        "news_headline": "China announces $500B infrastructure stimulus targeting steel-intensive construction",
        "news_summary": "Beijing unveils major infrastructure spending focused on high-speed rail and urban development. Steel demand forecast +12% over next two quarters.",
        "market_signals": {
            "current_price": 51.50,
            "iron_ore_62fe": 128.0,
            "aud_usd": 0.70,
            "rsi_14": 44,
            "atr_14": 1.35,
            "support_levels": [50.00, 48.50, 47.00],
            "resistance_levels": [53.00, 55.00, 57.00],
            "ma_20": 50.80,
            "ma_50": 49.50,
            "ma_200": 48.00,
        },
    },
    {
        "label": "China property crisis (SELL)",
        "agent_votes": {"bullish": 3, "bearish": 37, "neutral": 5},
        "news_headline": "China property developers default, steel demand collapses 20%",
        "news_summary": "Three major Chinese property developers announce simultaneous defaults. Construction activity halts across 150+ projects. Iron ore futures down 7% overnight.",
        "market_signals": {
            "current_price": 49.80,
            "iron_ore_62fe": 95.0,
            "aud_usd": 0.63,
            "rsi_14": 71,
            "atr_14": 1.80,
            "support_levels": [48.00, 46.00, 44.00],
            "resistance_levels": [51.00, 53.00, 55.00],
            "ma_20": 52.10,
            "ma_50": 53.50,
            "ma_200": 54.00,
        },
    },
    {
        "label": "Geopolitical noise only (WAIT)",
        "agent_votes": {"bullish": 14, "bearish": 13, "neutral": 18},
        "news_headline": "Middle East tensions rise as regional conflict spreads",
        "news_summary": "Geopolitical tensions in the Middle East escalate. Oil prices spike. No direct impact on Australian iron ore routes confirmed.",
        "market_signals": {
            "current_price": 50.20,
            "iron_ore_62fe": 112.0,
            "aud_usd": 0.67,
            "rsi_14": 52,
            "atr_14": 1.10,
            "support_levels": [49.00, 47.50, 46.00],
            "resistance_levels": [52.00, 54.00, 56.00],
            "ma_20": 50.50,
            "ma_50": 50.00,
            "ma_200": 49.20,
        },
    },
    {
        "label": "RBA rate hike (mild bearish)",
        "agent_votes": {"bullish": 8, "bearish": 25, "neutral": 12},
        "news_headline": "RBA raises cash rate 25bp to 4.60%, signals further hikes possible",
        "news_summary": "Reserve Bank of Australia raises interest rates for the 14th time. AUD strengthens against USD. Mining cost pressures increase via higher financing costs.",
        "market_signals": {
            "current_price": 50.90,
            "iron_ore_62fe": 109.0,
            "aud_usd": 0.695,
            "rsi_14": 58,
            "atr_14": 1.20,
            "support_levels": [49.50, 48.00, 46.50],
            "resistance_levels": [52.50, 54.00, 56.50],
            "ma_20": 51.20,
            "ma_50": 50.80,
            "ma_200": 49.80,
        },
    },
    {
        "label": "Iron ore supply disruption (BUY)",
        "agent_votes": {"bullish": 28, "bearish": 6, "neutral": 11},
        "news_headline": "Cyclone forces closure of Port Hedland for 5 days, iron ore supply disrupted",
        "news_summary": "Category 4 cyclone forces temporary closure of Port Hedland, the world's largest iron ore export terminal. An estimated 12Mt of shipments delayed. Iron ore spot price jumps 4%.",
        "market_signals": {
            "current_price": 52.30,
            "iron_ore_62fe": 122.0,
            "aud_usd": 0.68,
            "rsi_14": 48,
            "atr_14": 1.55,
            "support_levels": [51.00, 49.50, 48.00],
            "resistance_levels": [54.00, 56.00, 58.00],
            "ma_20": 51.50,
            "ma_50": 50.20,
            "ma_200": 49.00,
        },
    },
    {
        "label": "Mild China PMI improvement (BUY test — memory should be active)",
        "agent_votes": {"bullish": 22, "bearish": 9, "neutral": 14},
        "news_headline": "China Caixin PMI rises to 51.2, first expansion in 4 months",
        "news_summary": "China manufacturing activity returns to expansion territory. Steel mill capacity utilisation rises to 82%. Iron ore port inventories draw down 4Mt from prior week.",
        "market_signals": {
            "current_price": 51.20,
            "iron_ore_62fe": 115.0,
            "aud_usd": 0.69,
            "rsi_14": 50,
            "atr_14": 1.25,
            "support_levels": [50.00, 48.50, 47.00],
            "resistance_levels": [53.00, 55.00, 57.00],
            "ma_20": 50.90,
            "ma_50": 49.80,
            "ma_200": 48.50,
        },
    },
]


def post_prediction(scenario: dict, index: int) -> dict:
    payload = json.dumps({
        "stock_ticker": "BHP.AX",
        "news_headline": scenario["news_headline"],
        "news_summary": scenario["news_summary"],
        "market_signals": scenario["market_signals"],
        "agent_votes": scenario["agent_votes"],
        "generate_trade_execution": True,
        "use_memory": True,
        "broadcast_signal": False,
        "risk_tolerance": "moderate",
    }).encode()

    req = urllib.request.Request(
        f"{BACKEND_URL}/api/reasoning/synthesize",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  [ERROR] HTTP {e.code}: {body[:200]}")
        return {}
    except Exception as e:
        print(f"  [ERROR] {e}")
        return {}

    direction = data.get("prediction", {}).get("final_decision", {}).get("direction", "?")
    confidence = data.get("prediction", {}).get("final_decision", {}).get("confidence_score", "?")
    memory_applied = data.get("memory_applied", False)
    adjustments = data.get("prediction", {}).get("adjustments_applied", [])
    pred_id = data.get("prediction_id", "?")

    print(f"  Direction: {direction} | Confidence: {confidence}% | Memory: {'YES' if memory_applied else 'no'} | ID: {pred_id}")
    if adjustments:
        for adj in adjustments:
            print(f"  Adjustment: [{adj['type']}] {adj.get('original', '?')}% → {adj.get('adjusted', '?')}% — {adj.get('reason', '')}")

    return data


def main():
    if not API_KEY:
        print("ERROR: Set MARKET_ORACLE_API_KEY (or REACT_APP_API_KEY) env var")
        sys.exit(1)

    print(f"Seeding memory for BHP.AX — {len(SCENARIOS)} predictions")
    print(f"Backend: {BACKEND_URL}\n")

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"[{i}/{len(SCENARIOS)}] {scenario['label']}")
        result = post_prediction(scenario, i)

        if i < len(SCENARIOS):
            print("  Waiting 3s...\n")
            time.sleep(3)

    print("\nDone. Run the 6th (last) scenario again to see memory influence:")
    print("  memory_applied should be True")
    print("  adjustments_applied should show confidence calibration")
    print("  Footer: '🧠 Memory: Applied'\n")


if __name__ == "__main__":
    main()
