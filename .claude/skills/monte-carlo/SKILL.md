---
description: Run Monte Carlo simulations for signal stability validation. Trigger when calculating confidence intervals, stress testing predictions, or validating signal robustness.
globs:
  - "backend/routes/quant.py"
  - "backend/services/quant*.py"
---

# Monte Carlo Simulation Skill

## Purpose
Validate signal stability by running 2,500 simulations with parameter perturbation.
A signal is only published if the consensus direction holds under noise.

## Configuration
```python
MC_CONFIG = {
    "num_simulations": 2500,          # Reduced from 10,000 for speed
    "confidence_perturbation": 0.05,  # ±5% noise on agent confidence
    "price_perturbation": 0.02,       # ±2% noise on input prices
    "stability_threshold": 0.30,      # Minimum 30% stability required
}
```

## Stability Calculation

```python
def calculate_stability(simulations: list[SimulationResult]) -> float:
    """
    Stability = % of simulations agreeing with the consensus direction.

    Example:
      2500 total simulations
      Consensus: BULLISH
      1875 also say BULLISH
      Stability = 1875 / 2500 = 75%
    """
    consensus_direction = get_consensus(simulations)
    agreeing = sum(1 for s in simulations if s.direction == consensus_direction)
    return agreeing / len(simulations)
```

## Signal Quality Gates

| Metric | Threshold | Action if Failed |
|--------|-----------|------------------|
| Agent confidence | < 55% | Block signal |
| MC stability | < 30% | Block signal |
| Agent consensus agreement | < 60% | Add warning flag |

## Where Results Are Stored

MC results are stored in `simulations.full_json`:
```json
{
  "monte_carlo_price": {
    "price_stability_score": 0.72,
    "stability_score": 0.72,
    "confidence_interval_low": 44.1,
    "confidence_interval_high": 47.3,
    "simulations_run": 2500
  }
}
```

The `check_monte_carlo_instability` alert in `monitoring/alerts.py` reads
`price_stability_score`, `stability_score`, or `stability` from this field.

## Performance Profile

- Current: ~2,500 sims, semaphore=10, ~5 min total
- Target: ~45 seconds (reduce LLM calls, cache macro data)
- Optimization levers: increase semaphore, use Haiku for noise agents

## References
- `backend/routes/quant.py` — Monte Carlo endpoint
- `backend/monitoring/alerts.py` — `check_monte_carlo_instability()`

## Gotchas

### Zero Stability Bug
- **Symptom**: MC stability = 0% on otherwise valid signals
- **Cause**: Perturbation too high — consensus flipped randomly each run
- **Fix**: Reduced perturbation from 10% → 5%

### Missing Stability Field
- **Bug**: `check_monte_carlo_instability` found no stability data in full_json
- **Cause**: MC engine used inconsistent key names across versions
- **Fix**: Alert code tries `price_stability_score`, `stability_score`, `stability` in order
