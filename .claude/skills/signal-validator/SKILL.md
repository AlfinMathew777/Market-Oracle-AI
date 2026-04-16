---
description: Validate prediction outcomes against actual price movements. Trigger when checking prediction accuracy, running validation jobs, or generating accuracy reports.
globs:
  - "backend/validation/**/*.py"
  - "backend/routes/admin.py"
---

# Signal Validator Skill

## Validation Logic

```python
def _determine_outcome(predicted_direction, entry_price, exit_price):
    """
    Returns ('CORRECT' | 'INCORRECT' | 'NEUTRAL', change_pct)

    Threshold: ±0.5% minimum move to count as directional.
    Neutral predictions always return NEUTRAL regardless of move size.
    """
    change_pct = (exit_price - entry_price) / entry_price * 100
    direction = predicted_direction.lower()

    if direction == "neutral":
        return "NEUTRAL", change_pct

    moved_up   = change_pct > 0.5
    moved_down = change_pct < -0.5

    if not (moved_up or moved_down):
        return "NEUTRAL", change_pct   # Too small to call

    is_bullish = direction in ("bullish", "up", "buy")
    is_bearish = direction in ("bearish", "down", "sell")

    if is_bullish and moved_up:   return "CORRECT",   change_pct
    if is_bearish and moved_down: return "CORRECT",   change_pct
    return "INCORRECT", change_pct
```

## Validation Timing

- Validate predictions **24 hours after signal**
- Only validate on **ASX trading days** (skip weekends/holidays)
- Market hours: 10:00-16:00 AEST
- Snap to next market open if 24h lands outside trading hours

## Two Resolver Systems (Do Not Confuse)

| System | File | Horizon | When to Use |
|--------|------|---------|-------------|
| 24h validator | `validation/outcome_checker.py` | 24 hours | Fast feedback loop |
| 7-day resolver | `services/prediction_resolver.py` | 7 days | Authoritative accuracy |

Both write to `prediction_log.prediction_correct`. The 24h validator only
touches rows where `resolved_at IS NULL` — so they don't conflict.

## Metrics

### Hit Rate
```python
hit_rate = correct / (correct + incorrect)   # Exclude NEUTRAL from denominator
```

### Confidence Bands Used in Reports
- 55–65%
- 65–75%
- 75–85%
- 85%+

## Key Database Column

`bhp_price_at_prediction` — misleading name. Stores the entry price for
**any ticker**, not just BHP. This is a legacy naming issue. Don't refactor
without checking all query sites.

## Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /api/admin/validate-predictions` | API key | Trigger 24h job |
| `GET /api/metrics/validation-summary?days=30` | None | Accuracy breakdown |

## Gotchas

### Weekend Validation
- **Bug**: Validating Friday signals on Saturday (no price data available)
- **Fix**: `_next_market_open()` snaps target time to Monday 10:00 AEST

### NEUTRAL Counting
- NEUTRAL outcomes are stored as `prediction_correct = NULL` (not 0)
- They are excluded from hit-rate denominators
- This matches the existing 7-day resolver behaviour — keep consistent
