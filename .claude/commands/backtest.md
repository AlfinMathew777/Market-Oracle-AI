Run a historical backtest to validate prediction accuracy on past ASX data.

## Usage
```
/backtest BHP.AX 2025-01-01 2025-12-31
/backtest CBA.AX --period 6mo
/backtest --ticker BHP.AX RIO.AX --period 3mo
```

## Arguments
- `$TICKER` — ASX ticker (e.g. `BHP.AX`)
- `$START` — Start date (YYYY-MM-DD)
- `$END` — End date (YYYY-MM-DD), defaults to yesterday
- `--period` — Shorthand: `3mo`, `6mo`, `1y`

## What This Does

1. Fetches historical OHLCV data via yfinance
2. Simulates predictions day-by-day using only data available on each date
3. Compares predicted direction to next-day actual price movement
4. Calculates: hit rate, Sharpe ratio, max drawdown, monthly breakdown

## Anti-Look-Ahead Bias

This is the most important rule in backtesting:
- On day D, only use data from days < D
- Never let future prices influence past predictions

## Output

Results saved to `reports/backtest-{ticker}-{date}.md` and printed to console.

## Minimum Periods
- Statistical significance: ≥ 6 months (≥120 trading days)
- Per-confidence-band: ≥ 30 predictions per band to be meaningful

## Performance Note

Full backtest with LLM agents is slow (~5min per month of data).
Run in background or use cached agent outputs for speed.
