---
paths:
  - "backend/scripts/test_core.py"
  - "backend/services/australian_impact_engine.py"
  - "backend/services/chokepoint_service.py"
---

# Simulation Engine Rules — Market Oracle AI

## Pipeline Order (CRITICAL — do not reorder)
1. Vote tally → n_bull, n_bear, n_neut
2. Confidence calculation (raw math)
3. Causal chain audit → may override direction (CHAIN_OVERRIDE)
4. Blind judge + reconciler → may override direction
5. Market session modifier → adjusts confidence
6. Minimum confidence guard → LAST. Only silences direction if chain_override_active=False.

## Confidence System
- Never output 100% confidence. Hard cap: 85%.
- Multi-factor formula: `CONF_MAX[order] × CHAIN_MULT[order] × SEVERITY_MULT[severity]`
- Impact orders: primary (max 75%), secondary (max 55%), tertiary (max 35%)
- chain_override_active=True bypasses the neutral guard — keep direction, add LOW_CONFIDENCE note

## Chokepoint Matrix Rules
- Iron ore travels NORTH through Lombok/Makassar Strait to China. NOT through Malacca. NOT through Suez.
- Malacca carries Middle East crude oil and Qatar LNG — NOT Australian iron ore.
- Malacca disruption = BULLISH WDS/STO (Qatar LNG competitor removed), NEUTRAL miners, BEARISH CBA (import inflation).
- Lombok = PRIMARY chokepoint for Australian iron ore. BHP/RIO/FMG = primary for Lombok, tertiary for Malacca/Suez.
- WDS/STO = primary for Lombok AND Suez. Competitive BULLISH for Malacca (Qatar LNG disrupted = Australian LNG premium).
- State heatmap: Suez = WA45/QLD20/NT15/NSW5/VIC0. Lombok = WA90/QLD20/NT30/NSW10. Malacca = WA15/QLD25/NT20/NSW20/VIC15.

## Encoding
- All string literals use `—` (em dash), never `?` or `→` artifacts.
- Confidence stored as 0.0–1.0 float, displayed as 0–100% integer.

## Adding New Chokepoints
- Add to `CHOKEPOINTS` in chokepoint_service.py
- Add to `CHOKEPOINT_AUSTRALIA_MATRIX` in australian_impact_engine.py
- Add to `_CHOKEPOINT_EXPOSURE` with commodity fractions
- Add to `_ASX_SECTOR_IMPACTS` with Energy/Materials/Financials/Industrials/Consumer
- Add to `_CHOKEPOINT_SEVERITY` and `_generate_key_insight()`
- Add to `_TICKER_IMPACT_OVERRIDE` for explicit order assignments
