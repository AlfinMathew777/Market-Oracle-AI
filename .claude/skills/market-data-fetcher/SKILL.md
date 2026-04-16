---
description: Fetch real-time and historical ASX stock data, macro indicators, and news. Trigger when user asks for prices, market data, or when simulation needs fresh data.
globs:
  - "backend/**/*.py"
  - "*.py"
---

# Market Data Fetcher Skill

## When to Use
- Fetching current ASX stock prices
- Getting historical OHLCV data for backtesting
- Pulling macro indicators (interest rates, commodities, AUD/USD)
- Checking data freshness before simulations

## Data Sources

### ASX Prices (yfinance)
```python
import yfinance as yf

# Single ticker
ticker = yf.Ticker("BHP.AX")
current_price = ticker.info.get('regularMarketPrice')
history = ticker.history(period="1mo")

# Multiple tickers
data = yf.download(["BHP.AX", "CBA.AX"], period="6mo")
```

### Macro Data (FRED)
```python
from fredapi import Fred
fred = Fred(api_key=os.getenv("FRED_API_KEY"))

# Key indicators
aus_interest = fred.get_series('INTDSRTRM193N')  # Australia interest rate
iron_ore     = fred.get_series('PIORECRUSDM')    # Iron ore price
aud_usd      = fred.get_series('DEXUSAL')        # AUD/USD exchange
```

### News (MarketAux / RSS aggregator)
- Check `backend/services/news_service.py` for MarketAux integration
- RSS feeds aggregated via `backend/services/asx_news_aggregator.py`
- Cached in Redis at `news:australia:v1`

## Critical Rules

1. **NEVER fabricate data** — if API fails, return error, don't hallucinate prices
2. **Check data freshness** — ASX trades 10am-4pm AEST, Mon-Fri
3. **Handle rate limits** — yfinance: 2000 req/hour, FRED: 120 req/min
4. **Cache when possible** — don't refetch same day's data repeatedly

## Gotchas

### yfinance Issues
- `.AX` suffix required for ASX tickers
- Weekend/holiday data returns last trading day
- `info` dict may have missing keys — always use `.get()`
- Rate limiting kicks in silently — add 0.5s delays between calls
- `fast_info` is faster than `info` for just the price

### FRED Issues
- Data is often delayed (monthly updates)
- Series IDs are cryptic — refer to references/fred-series.md
- Some series require FRED account for access

### Timezone
- ASX operates in AEST/AEDT (UTC+10/+11)
- Always convert: `datetime.now(ZoneInfo("Australia/Sydney"))`
- Market hours: 10:00-16:00 Sydney time
- Use `zoneinfo` (stdlib Python 3.9+), not `pytz`

## Error Handling

```python
def fetch_price_safe(ticker: str) -> Optional[float]:
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.last_price
        if price is None or price <= 0:
            logger.warning("Invalid price for %s", ticker)
            return None
        return float(price)
    except Exception as e:
        logger.error("Failed to fetch %s: %s", ticker, e)
        return None
```

## See Also
- `references/asx-tickers.md` — List of supported ASX tickers
- `references/fred-series.md` — FRED series IDs for macro data
- `gotchas.md` — Learned failures and fixes
- `backend/monitoring/data_health.py` — Feed staleness tracking
