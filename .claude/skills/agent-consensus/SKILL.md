---
description: Run the 45-agent adversarial debate system. Trigger when generating predictions, calculating consensus, or debugging agent disagreements.
globs:
  - "backend/agents/**/*.py"
  - "backend/scripts/test_core.py"
---

# Agent Consensus Skill

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   45-50 Agent System                     │
├─────────────────┬─────────────────┬─────────────────────┤
│   ~15 Bull      │   ~15 Bear      │   ~15 Neutral        │
│   Agents        │   Agents        │   Agents             │
│                 │                 │                      │
│ - Macro Bull    │ - Macro Bear    │ - Macro Neutral      │
│ - Sector Bull   │ - Sector Bear   │ - Sector Neutral     │
│ - Technical Bull│ - Technical Bear│ - Technical Neutral  │
│ - Sentiment Bull│ - Sentiment Bear│ - Sentiment Neutral  │
│ - Momentum Bull │ - Momentum Bear │ - Momentum Neutral   │
└────────┬────────┴────────┬────────┴──────────┬──────────┘
         │                 │                   │
         └─────────────────┼───────────────────┘
                           ▼
                  ┌─────────────────┐
                  │  Causal Chain   │  ← may override direction
                  │     Audit       │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │  Blind Judge +  │  ← may override direction
                  │   Reconciler    │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │  Monte Carlo    │  ← stability validation
                  │  Stability      │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Confidence Guard│  ← LAST step, hard caps
                  └─────────────────┘
```

## Simulation Pipeline Order (DO NOT REORDER)

1. Vote tally (n_bull, n_bear, n_neut)
2. Confidence calculation
3. **Causal chain audit** — may override direction
4. Blind judge + reconciler — may override direction
5. Market session modifier
6. **Minimum confidence guard** — LAST step

## Confidence System

- Hard cap: **85%** max. Never output 100%.
- Primary order: max 75% | Secondary: max 55% | Tertiary: max 35%
- `chain_override_active=True` bypasses neutral guard
- Minimum actionable: **55%**

## Causal Chain Examples

### Mining (BHP, RIO, FMG)
```
Iron ore ↑ → Revenue ↑ → BULLISH
China PMI ↑ → Demand signal → BULLISH
AUD/USD ↑ → USD revenue worth less in AUD → BEARISH
Lombok disruption → Exports blocked → BEARISH
Malacca disruption → NEUTRAL (doesn't affect iron ore routes)
```

### Banking (CBA, NAB, WBC, ANZ)
```
RBA rate ↑ → NIM ↑ but bad debts ↑ → MIXED
Housing prices ↑ → Collateral value ↑ → BULLISH
Unemployment ↑ → Loan defaults ↑ → BEARISH
Import inflation → Consumer stress → BEARISH
```

### Energy (WDS, STO)
```
LNG spot price ↑ → Revenue ↑ → BULLISH
Malacca disruption → Qatar LNG disrupted → Competitor removed → BULLISH
Lombok disruption → Own LNG shipments affected → MIXED
Oil ↑ → Energy demand signal → BULLISH
```

## Key Files

| File | Purpose |
|------|---------|
| `backend/scripts/test_core.py` | Main 45-agent simulation engine |
| `backend/routes/simulate.py` | `/api/simulate` endpoint |
| `backend/services/catalyst_validator.py` | Validates causal chains |
| `backend/services/prediction_resolver.py` | 7-day outcome resolver |

## Gotchas

### CBA.AX Mining Logic Bug (Fixed 2026-03)
- CBA was receiving iron ore causal chain instead of banking logic
- Always verify sector before applying causal chain

### Agent Hallucination on Data Failure
- Agents fabricated iron ore prices when yfinance was unavailable
- Fix: Data health gate in `backend/monitoring/data_health.py`
- Gate fires in `routes/simulate.py` before any agent is invoked
