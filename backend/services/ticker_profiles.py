"""Ticker-aware business profiles for ASX stocks.

Each profile tells agents WHAT the company does, WHAT drives its revenue,
and which geopolitical/commodity signals are relevant vs irrelevant.
Injected into every agent system prompt via build_ticker_context_block().
"""

from typing import Dict, Any, Optional

# ── Ticker profiles ────────────────────────────────────────────────────────────

_PROFILES: Dict[str, Dict[str, Any]] = {
    "BHP.AX": {
        "name": "BHP Group",
        "sector": "Diversified Mining",
        "primary_revenue_drivers": ["iron ore (50% revenue)", "copper (25%)", "coal (metallurgical)"],
        "key_sensitivities": [
            "China steel production → iron ore demand",
            "Iron ore 62% Fe spot price",
            "AUD/USD (revenues in USD, costs partly in AUD)",
            "Port Hedland throughput (iron ore export gateway)",
            "Energy transition → copper demand (long-term positive)",
        ],
        "irrelevant_signals": [
            "RBA rate decisions (minimal direct impact on BHP revenues)",
            "Australian housing market",
            "Retail spending data",
        ],
        "causal_chain_template": (
            "Event → {signal} → iron ore / copper demand impact "
            "→ BHP revenue and margin direction → BHP.AX price"
        ),
    },
    "RIO.AX": {
        "name": "Rio Tinto",
        "sector": "Diversified Mining",
        "primary_revenue_drivers": ["iron ore (60%+ revenue)", "aluminium (20%)", "copper"],
        "key_sensitivities": [
            "China steel production → iron ore demand",
            "Iron ore 62% Fe spot price",
            "Aluminium market (LME prices)",
            "AUD/USD (USD revenues vs AUD costs)",
            "Pilbara operations (iron ore export region)",
        ],
        "irrelevant_signals": [
            "RBA rate decisions",
            "Australian domestic retail or banking data",
        ],
        "causal_chain_template": (
            "Event → {signal} → iron ore / aluminium demand impact "
            "→ Rio Tinto earnings direction → RIO.AX price"
        ),
    },
    "FMG.AX": {
        "name": "Fortescue",
        "sector": "Iron Ore Mining",
        "primary_revenue_drivers": ["iron ore (>95% revenue — pure-play)", "iron ore price is the dominant variable"],
        "key_sensitivities": [
            "Iron ore 62% Fe spot price (single largest driver)",
            "China steel mill demand",
            "AUD/USD (all iron ore revenues in USD)",
            "Port Hedland shipments",
            "China property sector health (major steel consumer)",
        ],
        "irrelevant_signals": [
            "RBA rate decisions",
            "Australian banking or consumer data",
            "Copper or gold prices",
        ],
        "causal_chain_template": (
            "Event → iron ore price / China demand impact "
            "→ Fortescue revenue change → FMG.AX price"
        ),
    },
    "WDS.AX": {
        "name": "Woodside Energy",
        "sector": "Oil & Gas (LNG-focused)",
        "primary_revenue_drivers": ["LNG (liquefied natural gas, ~60%)", "oil", "domestic gas"],
        "key_sensitivities": [
            "LNG spot prices (JKM — Japan-Korea marker)",
            "Oil price (Brent Crude)",
            "Asia-Pacific LNG demand (Japan, Korea, China)",
            "Shipping route disruptions affecting LNG tankers",
            "AUD/USD (LNG contracts priced in USD)",
            "Middle East or Strait of Hormuz tensions (oil supply shock)",
        ],
        "irrelevant_signals": [
            "Iron ore prices",
            "China steel demand",
            "RBA rate decisions (for near-term direction)",
        ],
        "causal_chain_template": (
            "Event → LNG / oil price impact → Woodside revenue direction → WDS.AX price"
        ),
    },
    "STO.AX": {
        "name": "Santos",
        "sector": "Oil & Gas",
        "primary_revenue_drivers": ["LNG", "oil", "domestic gas", "Papua New Guinea LNG"],
        "key_sensitivities": [
            "Oil price (Brent Crude)",
            "LNG spot prices",
            "Asian energy demand",
            "Geopolitical supply disruptions (Middle East, Russia)",
        ],
        "irrelevant_signals": ["Iron ore", "Steel demand", "RBA rates for near-term direction"],
        "causal_chain_template": (
            "Event → oil / LNG price impact → Santos revenue direction → STO.AX price"
        ),
    },
    "CBA.AX": {
        "name": "Commonwealth Bank of Australia",
        "sector": "Banking (Retail & Business)",
        "primary_revenue_drivers": [
            "Net interest margin (NIM) — spread between lending and deposit rates",
            "Home loan book (~50% of loan book)",
            "Business lending",
            "Transaction fees and wealth management",
        ],
        "key_sensitivities": [
            "RBA cash rate (directly sets NIM and deposit/lending spread)",
            "Australian housing market (mortgage demand and arrears)",
            "Australian unemployment rate (credit quality)",
            "Consumer spending (card volumes and fee income)",
            "RBA rate cuts → NIM compression → BEARISH for bank earnings",
            "RBA rate hikes → NIM expansion → BULLISH for bank earnings",
        ],
        "irrelevant_signals": [
            "Iron ore prices (zero direct revenue link)",
            "China steel demand",
            "Port Hedland shipping",
            "Commodity prices generally",
            "AUD/USD (CBA revenues almost entirely AUD-denominated)",
        ],
        "causal_chain_template": (
            "Event → Australian interest rate / credit quality impact "
            "→ CBA net interest margin or loan book quality → CBA.AX price"
        ),
    },
    "WBC.AX": {
        "name": "Westpac Banking Corporation",
        "sector": "Banking (Retail & Business)",
        "primary_revenue_drivers": [
            "Net interest margin (NIM)",
            "Home loans and business lending",
            "Deposits and transaction fees",
        ],
        "key_sensitivities": [
            "RBA cash rate",
            "Australian housing market",
            "Consumer credit quality",
            "Australian unemployment",
        ],
        "irrelevant_signals": [
            "Iron ore, commodity prices, China steel demand",
            "AUD/USD (domestic revenue base)",
        ],
        "causal_chain_template": (
            "Event → RBA rate / Australian credit conditions → Westpac NIM or arrears → WBC.AX price"
        ),
    },
    "NCM.AX": {
        "name": "Newcrest Mining",
        "sector": "Gold Mining",
        "primary_revenue_drivers": ["gold (primary)", "copper (secondary)"],
        "key_sensitivities": [
            "Gold spot price (USD/oz) — dominant driver",
            "USD strength (gold priced in USD, inverse correlation)",
            "Real interest rates (higher rates = lower gold)",
            "Risk-off sentiment (gold as safe haven)",
        ],
        "irrelevant_signals": ["Iron ore", "Steel", "LNG", "RBA rates for NIM"],
        "causal_chain_template": (
            "Event → risk sentiment / USD / real rates → gold price → Newcrest revenue → NCM.AX price"
        ),
    },
    "MIN.AX": {
        "name": "Mineral Resources",
        "sector": "Lithium & Iron Ore Mining",
        "primary_revenue_drivers": ["lithium (growing)", "iron ore", "mining services"],
        "key_sensitivities": [
            "Lithium carbonate / spodumene price",
            "EV demand outlook (China and global)",
            "Iron ore spot price",
            "China battery supply chain",
        ],
        "irrelevant_signals": ["RBA rates", "Banking data"],
        "causal_chain_template": (
            "Event → lithium demand / iron ore price → MinRes revenue → MIN.AX price"
        ),
    },
    "TWE.AX": {
        "name": "Treasury Wine Estates",
        "sector": "Consumer Staples — Wine",
        "primary_revenue_drivers": ["premium wine (Americas, Asia)", "Penfolds (China market)"],
        "key_sensitivities": [
            "China tariff status on Australian wine",
            "Consumer confidence (premium goods)",
            "AUD/USD (export revenues in USD/CNY)",
            "China-Australia trade relations",
        ],
        "irrelevant_signals": ["Iron ore", "Gas", "RBA rates for near-term direction"],
        "causal_chain_template": (
            "Event → China trade / AUD impact → Treasury Wine export revenue → TWE.AX price"
        ),
    },
}

# Default generic profile for tickers without a specific entry
_DEFAULT_PROFILE: Dict[str, Any] = {
    "name": "Unknown ASX company",
    "sector": "Unknown",
    "primary_revenue_drivers": ["company-specific factors"],
    "key_sensitivities": ["earnings", "macro conditions"],
    "irrelevant_signals": [],
    "causal_chain_template": "Event → macro/sector impact → {ticker} price",
}


def get_profile(ticker: str) -> Dict[str, Any]:
    """Return the profile dict for a ticker, falling back to the default."""
    return _PROFILES.get(ticker, _DEFAULT_PROFILE)


def build_ticker_context_block(ticker: str) -> str:
    """
    Build a plain-text context block injected into every agent system prompt.
    Tells agents exactly what business the company is in so they don't apply
    mining logic to a bank or vice versa.
    """
    p = get_profile(ticker)
    drivers = "\n".join(f"  - {d}" for d in p["primary_revenue_drivers"])
    sensitivities = "\n".join(f"  - {s}" for s in p["key_sensitivities"])
    irrelevant = (
        "\n".join(f"  - {s}" for s in p["irrelevant_signals"])
        if p["irrelevant_signals"]
        else "  (none specified)"
    )

    return (
        f"=== TICKER PROFILE: {ticker} ({p['name']}) ===\n"
        f"Sector: {p['sector']}\n"
        f"PRIMARY REVENUE DRIVERS (what actually moves this stock's earnings):\n{drivers}\n"
        f"KEY MARKET SENSITIVITIES (signals you MUST analyse):\n{sensitivities}\n"
        f"IRRELEVANT SIGNALS (DO NOT use these as primary reasoning for {ticker}):\n{irrelevant}\n"
        f"CAUSAL CHAIN: {p['causal_chain_template']}\n"
        f"=== END TICKER PROFILE ==="
    )
