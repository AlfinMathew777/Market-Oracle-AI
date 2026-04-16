Validate pending prediction outcomes against actual ASX price movements.

## Usage
```
/validate
/validate --summary
```

## What This Does

Triggers the 24-hour outcome validator which:
1. Finds all prediction_log rows where `prediction_correct IS NULL` and age > 24h
2. Fetches actual ASX prices via yfinance at signal_time + 24h
3. Compares predicted direction to actual movement (threshold: ±0.5%)
4. Writes CORRECT / INCORRECT / NEUTRAL to the database
5. Returns a summary with hit rate and breakdown

## API Call
```bash
curl -X POST http://localhost:8000/api/admin/validate-predictions \
  -H "X-API-Key: $MARKET_ORACLE_API_KEY"
```

## Accuracy Summary
```bash
# Last 30 days (default)
curl http://localhost:8000/api/metrics/validation-summary

# Last 7 days
curl "http://localhost:8000/api/metrics/validation-summary?days=7"
```

## Expected Output
```json
{
  "validated": 15,
  "correct": 10,
  "incorrect": 4,
  "neutral": 1,
  "hit_rate": 0.714,
  "by_confidence_band": {
    "55-65%": {"total": 5, "hit_rate": 0.60},
    "65-75%": {"total": 7, "hit_rate": 0.71},
    "75-85%": {"total": 3, "hit_rate": 0.85}
  }
}
```

## Notes
- NEUTRAL outcomes are skipped — they don't count in hit rate numerator or denominator
- Only processes predictions with `excluded_from_stats = 0 or NULL`
- ASX weekend signals snap to Monday 10:00 AEST for price fetch
