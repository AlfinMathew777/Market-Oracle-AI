# Validation Layer Audit
**Date:** 2026-04-17  
**Scope:** `prediction_log` direction naming, 62 vs 86 row mismatch, neutral scoring bug  
**Status:** Phase 1 complete — authorises Phase 2 onward

---

## 1. Direction Value Distribution

Resolved rows only (`prediction_correct IS NOT NULL`, n=86):

| Token    | excl=0 (in stats) | excl=1 (dropped) | Total | Hit rate (excl=0, non-neutral) |
|----------|-------------------|------------------|-------|-------------------------------|
| bullish  | 41                | 1                | 42    | 61.0% (25/41)                 |
| bearish  | 10                | 1                | 11    | 20.0% (2/10)                  |
| up       | 7                 | 1                | 8     | 100% (7/7)                    |
| down     | 4                 | 3                | 7     | 0% (0/4)                      |
| neutral  | 4                 | 14               | 18    | N/A — scored 0 (BUG)          |
| **Total**| **66**            | **20**           | **86**|                               |

Two distinct direction vocabularies exist in the DB:
- `bullish` / `bearish` / `neutral` — standard vocabulary (new code path)
- `up` / `down` / `neutral` — legacy vocabulary (old code path)

---

## 2. All Writers and Their Conventions

### Writer 1: `database.py:save_prediction_log()` (line 600)
- **Convention:** normalises on write — `{"UP": "bullish", "DOWN": "bearish", "NEUTRAL": "neutral"}.get(direction.upper(), direction.lower())`
- **Exclusion logic:** applies `_is_garbage_prediction()` gate — sets `excluded_from_stats=1` + `exclusion_reason` for low-confidence predictions
- **Used by:** the main simulation pipeline (`routes/simulate.py` → `test_core.py` → `database.save_prediction_log`)

### Writer 2: `test_core.py:_save_prediction()` (line 2580)
- **Convention:** writes `direction.lower()` directly — where `direction` is the uppercase internal form (`"UP"`, `"DOWN"`, `"NEUTRAL"`), producing `"up"`, `"down"`, `"neutral"`
- **Exclusion logic:** NONE — does not set `excluded_from_stats` or `exclusion_reason`
- **Used by:** legacy/standalone test_core runs; all April 9 `up`/`down` rows originate here

**Root cause of vocabulary split:** Writer 2 is a legacy INSERT that was never updated when Writer 1 added normalisation. Both write to the same table with incompatible conventions.

---

## 3. Validator Comparison Logic (outcome_checker.py)

```python
# Lines 203-204 — direction aliases at READ time
is_bullish = direction in ("bullish", "up", "buy")
is_bearish = direction in ("bearish", "down", "sell")
```

The validator already handles both vocabularies. The `up`/`down` rows are **scored correctly** — the 100%/0% hit rates for `up`/`down` respectively reflect that BHP happened to rise on the April 9 batch date. This is **small-sample coincidence, not a scoring bug**.

---

## 4. Summary-Endpoint SQL Query

`get_validation_summary()` in `validation/outcome_checker.py` applies three filters:

```sql
-- Filter 1: date window (default 30 days)
AND resolved_at >= ?

-- Filter 2: exclude low-quality predictions
AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)

-- Filter 3: exclude neutral (no directional prediction)
AND predicted_direction NOT IN ('neutral')
```

The `database.py` duplicate at line ~705 applies the same Filter 2 + Filter 3 pattern.

---

## 5. Path from 86 to 62 (the 24 dropped rows)

```
86  total resolved (prediction_correct IS NOT NULL)
-20 excluded via excluded_from_stats=1
    ├── 13 rows: "Zero confidence — no signal (minimum confidence guard triggered)"
    └──  7 rows: "Confidence below 5% minimum threshold"
-4  excluded via predicted_direction NOT IN ('neutral') [excl=0 neutral rows]
────
62  rows visible in /api/metrics/validation-summary  ✓
```

The date window (30d) is **not** the cause — all 86 rows were created within the last 30 days.

---

## 6. Neutral Scoring Bug

All 18 neutral-direction rows have `prediction_correct=0` (scored as INCORRECT).  
Neutral predictions have no directional claim — they should carry `prediction_correct=NULL`.

**Impact on displayed stats:** Currently zero. The API filters neutrals out via `NOT IN ('neutral')`.  
**Impact on raw SQL queries:** Inflates "incorrect" counts. Direct `SELECT prediction_correct` queries return misleading accuracy figures.

Rows affected: 14 with `excluded_from_stats=1`, 4 with `excluded_from_stats=0`.

---

## 7. Phase 2 Authorisation

The direction naming bug IS real:
- Two writers with incompatible conventions exist (Writer 1 normalises; Writer 2 does not)
- `"up"` and `"down"` tokens appear in the live DB alongside `"bullish"`/`"bearish"`
- The validator handles both at read time, but there is no single authoritative mapping module

**Proceed to Phase 2** (create `direction_normalizer.py`) and Phase 3 (fix neutral scoring bug).

---

## 8. What Phase 2–6 Must Fix

| # | Issue | Fix |
|---|-------|-----|
| 1 | Two direction vocabularies | Phase 2: centralise in `direction_normalizer.py` |
| 2 | Neutral rows scored as INCORRECT | Phase 3: `_determine_outcome` returns "UNVALIDATABLE" for neutral; Phase 4: revalidate |
| 3 | Writer 2 bypasses normalisation | Phase 3: update Writer 2 to use normalizer; or document as deprecated |
| 4 | API shows 62 but raw SQL shows 86 | Phase 5: expose `excluded_count` and `unvalidatable_count` in summary response |
