# Signal Quality Rules

## Hard Thresholds (Never Override)

| Gate | Threshold | Action |
|------|-----------|--------|
| Confidence floor | < 55% | Block signal, log as excluded |
| Monte Carlo stability | < 30% | Block signal, log as excluded |
| Data feed stale | any critical feed > 30 min | Block simulation entirely |
| Kill switch | active | HTTP 503 on all simulate endpoints |

## Confidence Caps by Signal Order

| Order | Max Confidence |
|-------|---------------|
| Primary (first signal of session) | 75% |
| Secondary | 55% |
| Tertiary | 35% |
| Absolute hard cap | 85% |

Never output 100% confidence under any circumstances.

## Direction Override Rules

Causal chain audit may override agent vote consensus:
- `chain_override_active=True` bypasses neutral guard
- Record `chain_override_active` in prediction_log for auditability

## Signal Blocking Conditions

Block signals entirely (return HTTP 503) when:
- `is_signals_enabled() == False` (kill switch)
- `should_block_signals() == (True, reason)` (data health gate)
- PAPER_MODE does NOT block signals — it only suppresses publishing

## Required Logging Per Signal

Every generated signal MUST log:
- Ticker
- Direction (bullish/bearish/neutral)
- Confidence (0.0-1.0)
- Monte Carlo stability score
- Price at signal time (`bhp_price_at_prediction`)
- Timestamp (`predicted_at`)
- Paper mode flag
- Agent vote counts (bullish/bearish/neutral)
- Whether chain_override was active

## NEUTRAL Signal Handling

NEUTRAL predictions:
- Are logged to prediction_log
- Are excluded from accuracy hit-rate calculations
- Are NOT published even in live mode (nothing to act on)
- `prediction_correct` stored as NULL for neutrals
