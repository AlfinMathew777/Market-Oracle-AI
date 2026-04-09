"""
Seed Bank Memory Script
-----------------------
Runs 6 CBA.AX reasoning predictions to build enough history for
PredictionMemory to activate confidence calibration for bank stocks.

Usage:
    cd backend
    python scripts/seed_bank_memory.py

Requires:
    - Backend running on localhost:8000 (or set BACKEND_URL env var)
    - MARKET_ORACLE_API_KEY set
"""

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
        "label": "RBA rate hold, signals plateau through 2026 (NEUTRAL/HOLD)",
        "agent_votes": {"bullish": 15, "bearish": 18, "neutral": 12},
        "news_headline": "RBA holds rates steady at 4.35%, signals no cuts until late 2026",
        "news_summary": "Reserve Bank maintains cash rate citing persistent services inflation at 4.6%. Forward guidance implies rates plateau through 2026. Wholesale funding costs stable, deposit competition moderate.",
        "market_signals": {"current_price": 114.50, "rba_cash_rate": 4.35, "yield_curve_spread": 0.38},
    },
    {
        "label": "Housing rebound — mortgage apps surge (BUY)",
        "agent_votes": {"bullish": 28, "bearish": 8, "neutral": 9},
        "news_headline": "Mortgage applications surge 15% MoM as buyers anticipate RBA easing",
        "news_summary": "ABS data shows mortgage applications +15% MoM. Sydney auction clearance rates 76%, Melbourne 72%. New listings up 9%. Housing credit growth re-accelerating to 5.2% YoY annualised.",
        "market_signals": {"current_price": 115.80, "mortgage_growth_pct": 15.0, "housing_turnover_yoy": 9.0},
    },
    {
        "label": "Rising bad debts — SME defaults increase (SELL)",
        "agent_votes": {"bullish": 5, "bearish": 32, "neutral": 8},
        "news_headline": "Major banks provision additional $1.2B as SME defaults rise 25% YoY",
        "news_summary": "Big four banks collectively set aside $1.2B in additional bad debt provisions. SME default rate rises to 2.5% (vs 2.0% prior year). Commercial property exposure flagged as secondary risk.",
        "market_signals": {"current_price": 113.20, "bad_debt_ratio": 0.18, "sme_default_rate": 2.5},
    },
    {
        "label": "Record profit + NIM expansion (BUY)",
        "agent_votes": {"bullish": 35, "bearish": 3, "neutral": 7},
        "news_headline": "CBA posts $10.2B record profit, NIM expands 5bps to 2.07%, dividend raised 8%",
        "news_summary": "Commonwealth Bank FY result beats consensus. NIM at 2.07% (+5bps vs prior year). Dividend increased to $4.65 per share. Management guides stable margins for FY27. CET1 ratio 12.4%.",
        "market_signals": {"current_price": 118.40, "nim": 2.07, "cet1_ratio": 12.4, "dividend_yield": 4.2},
    },
    {
        "label": "APRA capital tightening — dividend pressure (SELL)",
        "agent_votes": {"bullish": 8, "bearish": 25, "neutral": 12},
        "news_headline": "APRA increases CET1 requirement by 50bps effective 2027, pressuring dividends",
        "news_summary": "Australian Prudential Regulation Authority announces 50bps uplift in minimum CET1 capital requirement effective January 2027. Banks may need to retain more earnings, reducing dividend capacity by an estimated 10-15%.",
        "market_signals": {"current_price": 112.60, "cet1_ratio": 12.3, "capital_requirement_change_bps": 50},
    },
    {
        "label": "Consumer confidence recovery + inflation cooling (BUY — memory should activate)",
        "agent_votes": {"bullish": 22, "bearish": 10, "neutral": 13},
        "news_headline": "Consumer confidence hits 18-month high as inflation moderates to 3.2%",
        "news_summary": "Westpac-MI Consumer Sentiment index rises to 94.2, highest since October 2024. CPI trimmed mean at 3.2% (below RBA 3.5% forecast). Retail spending +1.8% MoM. Mortgage stress indicators ease.",
        "market_signals": {"current_price": 116.20, "consumer_confidence": 94.2, "cpi_trimmed_mean": 3.2},
    },
]


def post_prediction(scenario: dict, index: int) -> dict:
    payload = json.dumps({
        "stock_ticker": "CBA.AX",
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
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
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

    fd = data.get("prediction", {}).get("final_decision", {})
    direction = fd.get("direction", "?")
    confidence = fd.get("confidence_score", "?")
    memory_applied = data.get("memory_applied", False)
    adjustments = data.get("prediction", {}).get("adjustments_applied", [])
    pred_id = (data.get("prediction_id") or "?")[:8]

    print(f"  {direction} | {confidence}% confidence | Memory: {'YES' if memory_applied else 'no'} | ID: {pred_id}…")
    for adj in adjustments:
        print(f"    Adj [{adj['type']}]: {adj.get('original', '?')}% → {adj.get('adjusted', '?')}% — {adj.get('reason', '')}")

    return data


def main():
    if not API_KEY:
        print("ERROR: Set MARKET_ORACLE_API_KEY (or REACT_APP_API_KEY) env var")
        sys.exit(1)

    print(f"Seeding CBA.AX bank memory — {len(SCENARIOS)} predictions")
    print(f"Backend: {BACKEND_URL}\n")

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"[{i}/{len(SCENARIOS)}] {scenario['label']}")
        post_prediction(scenario, i)
        if i < len(SCENARIOS):
            print("  Waiting 3s…\n")
            time.sleep(3)

    print("\nDone. The next CBA.AX prediction should show:")
    print("  memory_applied: True")
    print("  adjustments_applied: confidence calibration entries")
    print("  Footer: '🧠 Memory: Applied'\n")
    print("Run a test prediction:")
    print(f"  python scripts/seed_bank_memory.py  (re-run to see memory influence on scenario 6)")


if __name__ == "__main__":
    main()
