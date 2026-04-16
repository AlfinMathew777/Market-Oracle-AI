---
description: Australian Securities Exchange domain knowledge. Trigger when needing ASX-specific rules, trading hours, holidays, sector logic, or geographic trade routes.
globs:
  - "**/*.py"
  - "**/*.md"
---

# ASX Knowledge Skill

## Trading Hours (Sydney / AEST)
- **Pre-open**: 7:00 – 10:00 AEST
- **Normal trading**: 10:00 – 16:00 AEST
- **Post-market**: 16:00 – 16:10 AEST
- Weekends: Closed
- Public holidays: Closed (see below)

## 2026 ASX Holidays
```python
ASX_HOLIDAYS_2026 = [
    "2026-01-01",  # New Year's Day
    "2026-01-26",  # Australia Day
    "2026-04-03",  # Good Friday
    "2026-04-06",  # Easter Monday
    "2026-04-25",  # ANZAC Day
    "2026-06-08",  # King's Birthday (NSW/VIC/QLD/SA/TAS/ACT)
    "2026-12-25",  # Christmas Day
    "2026-12-28",  # Boxing Day (observed)
]
```

## Ticker Format
- ASX tickers require `.AX` suffix in yfinance
- Example: `BHP.AX`, `CBA.AX`, `WDS.AX`
- Without `.AX`, yfinance returns US prices

## Critical Geographic Facts (Do Not Contradict)

### Iron Ore Shipping Routes
- Australian iron ore travels **NORTH** through **Lombok/Makassar Strait** to China
- Australian iron ore does **NOT** transit Malacca Strait
- Malacca carries: Middle East crude oil, Qatar LNG

### Chokepoint → ASX Impact Matrix

| Chokepoint | BHP/RIO/FMG | WDS/STO | CBA | Notes |
|------------|-------------|---------|-----|-------|
| Lombok (blocked) | Bearish | Mixed | Neutral | Iron ore route blocked |
| Malacca (blocked) | Neutral | **Bullish** | Bearish | Qatar LNG competitor removed; import inflation |
| Suez (blocked) | Bearish (secondary) | Bearish | Bearish | LNG rerouting; global inflation |

### State Heatmap (Economic Impact %)
| State | Lombok | Malacca | Suez |
|-------|--------|---------|------|
| WA | 90 | 15 | 45 |
| QLD | 20 | 25 | 20 |
| NT | 30 | 20 | 15 |
| NSW | 10 | 20 | 5 |
| VIC | 0 | 15 | 0 |

## Regulatory Context

### AFSL (Australian Financial Services Licence)
- **Providing financial advice requires AFSL**
- Market Oracle AI provides **predictions, not advice**
- Always frame as: "The system predicts..." not "You should buy/sell..."

### Correct Framing
- ✅ "The system predicts BHP may rise given iron ore +2.3%"
- ✅ "Historical hit rate: 65% over 90 days"
- ❌ "Buy BHP now"
- ❌ "This is a great investment opportunity"

## GICS Sector Classification

| Sector | Tickers | Primary Drivers |
|--------|---------|-----------------|
| Financials | CBA, NAB, WBC, ANZ, MQG | RBA rates, housing, credit |
| Materials | BHP, RIO, FMG | Iron ore, China PMI, AUD/USD |
| Energy | WDS, STO, ORG | LNG/oil price, shipping routes |
| Consumer Disc. | WES, ALL | Consumer sentiment, AUD |
| Consumer Staples | WOW, COL | Inflation, household spending |
| Health Care | CSL, RMD, COH | USD revenue (AUD/USD sensitive) |
| Industrials | TCL, BXB | Infrastructure spend |
| Real Estate | GMG, SCG | Interest rates, cap rates |
| Communication | TLS, REA | ARPU, property market |
| Technology | XRO, WTC, CPU | USD revenue, growth rates |
