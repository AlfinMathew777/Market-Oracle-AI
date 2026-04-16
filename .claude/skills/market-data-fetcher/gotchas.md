# Market Data Fetcher — Gotchas

## Learned Failures (most recent first)

### 2026-04-15: bhp_price_at_prediction Stores ANY Ticker's Price
- **Bug**: Column name suggests BHP-only but actually stores the simulated ticker's price
- **Reality**: `bhp_price_at_prediction` is the entry price for whatever ticker was predicted
- **Prevention**: Never assume column names are accurate — read the code, not the name

### 2026-04-10: Malacca Strait Geographic Error
- **Bug**: System treated Malacca Strait closure as bearish for Australian miners
- **Reality**: Australian iron ore ships via Lombok/Makassar Strait, NOT Malacca
- **Fix**: Malacca closure = BULLISH for WDS/STO (Qatar LNG competitor disrupted), NEUTRAL for BHP/RIO/FMG
- **Prevention**: Always verify geographic trade routes before causal reasoning
- **Key facts**: Iron ore → NORTH through Lombok/Makassar to China. Malacca carries Middle East oil.

### 2026-03-20: CBA.AX Mining Logic Applied to Banking
- **Bug**: CBA received iron ore causal chain instead of banking logic
- **Cause**: Sector lookup returned wrong value for CBA
- **Fix**: Explicit sector mapping in causal chain, not dynamic lookup
- **Prevention**: Each ticker has a hardcoded sector — never infer it

### 2026-03-15: yfinance Silent Stale Data
- **Bug**: yfinance returned stale data without any error
- **Symptom**: Predictions based on week-old prices
- **Fix**: Check `fast_info.last_price` timestamp, prefer `.history()` with explicit date range
- **Prevention**: Use `backend/monitoring/data_health.py` to track feed freshness

### 2026-02-28: FRED Rate Limiting (Silent)
- **Bug**: FRED silently returned empty series after rate limit
- **Fix**: Added exponential backoff; cache FRED data minimum 1 hour
- **Prevention**: Check response length before using — empty = likely rate-limited

### 2026-02-01: Weekend Price Handling
- **Bug**: Using Friday's price as "current" on Monday morning
- **Fix**: Snap to next market open via `_next_market_open()` in outcome_checker.py
- **Prevention**: Always validate trading day before price fetch
