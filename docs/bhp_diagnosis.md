# BHP / Market Oracle AI Prediction Diagnostic
**Date:** 2026-04-17  
**Trigger:** Production prediction revealed systematic accuracy issues.

---

## Phase 1 Findings

### Diagnostic 1 — Alt Data Endpoint Status

The `/api/data/alt-data/sample/BHP.AX` endpoint was implemented today and returns real
data. Verification requires a live server call. However code-level analysis (Diagnostic 2)
shows the data never reaches agents even when the endpoint works.

### Diagnostic 2 — Alt Data NOT Reaching Agents (Root Cause Found)

**File:** `backend/routes/simulate.py` — `_run_simulation_background()`  
**File:** `backend/scripts/test_core.py` — `Simulation.run_simulation()`

`event_data["alt_data"]` is populated correctly in `simulate.py` with a 15s timeout.
However, in `test_core.py` Step 3 (line ~1324), the `event_context` string passed to every
agent is built from only five fields:

```python
event_context = (
    f"Country: {event_data.get('country', 'Unknown')}\n"
    f"Event Type: {event_data.get('event_type', 'Unknown')}\n"
    f"Fatalities: {event_data.get('fatalities', 0)}\n"
    f"Date: {event_data.get('event_date', 'Unknown')}\n"
    f"Description: {event_data.get('notes', event_data.get('location', 'No description'))}"
)
```

`event_data["alt_data"]` is **never included** in this string.  
The agents never see it. The reconciler (which generates the causal chain) also never
sees it. This is **Case B** from the prompt — alt_data is set but not referenced in prompts.

### Diagnostic 3 — Agent Prompts Don't Reference Alt Data

Zero agent prompt templates in `test_core.py` reference `alt_data`, `composite_signal`,
or any of the five alternative data source summaries. The reconciler prompt
(`_reconciler_prompt`) receives only:
- Vote tallies
- Blind judge verdict
- Market session
- Top critical news headline
- Lessons block
- Chain questions

No alternative data whatsoever. **This is why causal chain stages read "No data"
even when announcements, insider activity, and analyst signals are available.**

### Diagnostic 4 — Per-Ticker Accuracy (Local DB, resolved predictions only)

| Ticker | Total | Correct | Hit Rate |
|--------|-------|---------|----------|
| CBA.AX | 18    | 2       | **11.11%** |
| LYC.AX | 6     | 2       | 33.33%  |
| BHP.AX | 62    | 33      | 53.23%  |

**Finding:** CBA.AX is the systematic failure, not BHP.AX. BHP.AX at 53.23% is close to
random (50%) which is acceptable for a noisy market. CBA.AX at 11.11% is statistically
impossible to achieve randomly — it is anti-predictive, meaning the model has a systematic
directional error.

**CBA breakdown:**
- 14 bullish predictions → 0 correct (0% hit rate)
- 2 bearish predictions → 2 correct (100% hit rate)
- 2 neutral predictions → 0 correct (0% hit rate)

**Root cause identified (Bug #3):** When no sector-specific catalyst exists for CBA.AX,
the trigger becomes `"No Banking (Retail & Business)-specific catalyst identified for
CBA.AX in last 24h..."`. The `no_catalyst` check in `determine_direction()` only matches
`trigger_event.startswith("No major catalyst")`. It does NOT match the sector-specific
fallback format. So `no_catalyst = False`, the function skips the neutral path, and falls
through to `return "bullish" if bullish > bearish`. Since agents are weakly bullish by
default, the prediction is always bullish even when there's no real signal.

### Diagnostic 5 — Monte Carlo Calibration Disconnect

No `monte_carlo_stability` column exists in the local `prediction_log` table, so the
historical correlation query cannot run. However, code analysis reveals the bug:

`run_confidence_monte_carlo()` determines `is_stable` purely by bootstrap-resampling
agent votes:
```python
if dominant == "bearish":
    is_stable = direction_stability > 70
else:
    is_stable = direction_stability < 30  # bullish wins >70% of sims
```

With 58% bullish agents (15 bull / 10 bear / 2 neutral), bullish wins >70% of bootstrap
resamples → `is_stable = True` → MC reports "HIGH stability" → no penalty applied.

This can produce "99.8% stability" readings even when:
- Agent consensus is only 52–58% (barely above coin-flip)
- The causal chain has 0/4 populated slots
- The actual prediction is wrong

**The two metrics (MC stability and causal chain quality) are completely disconnected.**

---

## Bugs Fixed

### Bug #1 — Alt Data Not Reaching Agents

**Symptom:** Alt data summaries (ASX announcements, insider activity, analyst consensus,
retail sentiment, RBA macro) are fetched and stored in `event_data["alt_data"]` but never
appear in agent prompts or the reconciler's causal chain generation.

**Cause:** `event_context` string in `test_core.py` Step 3 only includes 5 event fields.
`alt_data` is never extracted into the string.

**Fix:** Append an `ALT DATA SIGNALS` section to `event_context` when `alt_data` is
populated, listing the composite signal and per-source summaries. The reconciler sees this
and can cite specific signals in cost/revenue/demand/sentiment slots.

**File:** `backend/scripts/test_core.py`, `run_simulation()` Step 3 (~line 1324)

---

### Bug #2 — Monte Carlo / Agent Calibration Disconnect

**Symptom:** MC reports "99.8% stable" on predictions with 52% agent consensus and empty
causal chains.

**Cause:** `is_stable` only checks bootstrap directional consistency, not absolute
consensus quality or causal chain completeness.

**Fix:** New function `calibrate_monte_carlo_confidence()` in `backend/quant/calibration.py`.
Caps MC-adjusted confidence when agent consensus < 55% or causal chain < 60% populated.
Applied in the MC section of `run_simulation()` to penalise the final confidence.

**File:** `backend/quant/calibration.py` (new), `backend/scripts/test_core.py` MC section

---

### Bug #3 — No-Catalyst Check Misses Sector-Specific Fallback Format

**Symptom:** CBA.AX predicted bullish 14 times with 0% accuracy when there is no
sector-specific catalyst. The prediction should be NEUTRAL in these cases.

**Cause:** `determine_direction()` checks `trigger_event.startswith("No major catalyst")`
to detect no-catalyst situations. But the sector-specific fallback uses the format
`"No Banking (Retail & Business)-specific catalyst identified for CBA.AX in last 24h"`,
which does NOT start with "No major catalyst". So `no_catalyst = False`, the neutral
path is skipped, and bullish is returned because agents are weakly bullish by default.

**Fix:** Extend `no_catalyst` check to match any trigger that starts with "No " and
contains "catalyst identified".

**File:** `backend/scripts/test_core.py`, `determine_direction()` function

---

## Expected Before/After

### Before (CBA.AX with no catalyst, UPTREND):
```
Trigger: "No Banking (Retail & Business)-specific catalyst identified for CBA.AX..."
no_catalyst = False  ← bug
Direction: bullish (agents 58.8% bull → fallthrough returns bullish)
MC stability: "HIGH" (58.8% bull always wins bootstrap)
```

### After:
```
Trigger: "No Banking (Retail & Business)-specific catalyst identified for CBA.AX..."
no_catalyst = True  ← fixed
Direction: NEUTRAL (no catalyst + any volume → neutral path triggered)
```

### Before (with alt_data populated):
```
event_context: Country / Event Type / Fatalities / Date / Description
Agent sees: NOTHING from alt data
Causal chain: "No data — assumed neutral impact" across all 4 slots
```

### After:
```
event_context: ... + ALT DATA SIGNALS block with composite signal and summaries
Agent sees: "ASX Announcements: BHP profit upgrade [PRICE SENSITIVE]"
Causal chain: references specific signals in revenue/demand slots
```
