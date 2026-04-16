Run a full Market Oracle AI prediction simulation for an ASX ticker.

## Usage
```
/simulate BHP.AX
/simulate CBA.AX "Iron ore prices surged 5% on China PMI beat"
/simulate WDS.AX "Malacca Strait shipping disruption reported"
```

## Arguments
- `$TICKER` — ASX ticker with .AX suffix (required if not in event description)
- `$EVENT` — Event description to simulate (optional, defaults to macro scan)

## What This Does

1. Checks kill switch status and data feed health
2. Fetches current price, iron ore, AUD/USD, and news
3. Runs 45-agent adversarial debate (bull/bear/neutral)
4. Applies causal chain audit for geographic accuracy
5. Runs 2,500 Monte Carlo simulations for stability
6. Returns direction + confidence + key factors

## Pre-flight Checks (Run Before Simulating)
```bash
# Kill switch?
curl http://localhost:8000/api/admin/status

# Data feeds healthy?
curl http://localhost:8000/api/health/data-feeds
```

## Signal Quality Thresholds
- Confidence < 55% → signal blocked (too uncertain)
- MC stability < 30% → signal blocked (unstable)
- Data feed stale → simulation blocked

## Geographic Rules (Never Contradict)
- Iron ore routes: **Lombok/Makassar** → China (NOT Malacca)
- Malacca disruption → BULLISH WDS/STO, NEUTRAL BHP/RIO/FMG
- Lombok disruption → BEARISH BHP/RIO/FMG

## Default Ticker
If no ticker provided: use `BHP.AX`
