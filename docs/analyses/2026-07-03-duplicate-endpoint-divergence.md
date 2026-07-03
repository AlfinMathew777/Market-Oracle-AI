# Duplicate-endpoint divergence sweep + Stage 2b byte-match — first execution

Status: EXECUTED 2026-07-03 · Verdict: **ANDON — accuracy and calibration
clusters diverge; 3 of 4 verify-script families diverge from endpoints** ·
Tools: `backend/scripts/verify/verify_duplicates.py` + the four Stage 2b
reconstruction scripts (rfc-worldclass §4 amendment 2, §5.1).

## Provenance

The deployed API host is unreachable (`asx.marketoracle.ai` = NXDOMAIN,
2026-07-03), so the sweep ran against the backend served LOCALLY
(uvicorn, development env) on top of the git-tracked production snapshot
(commit `e16532e`, rows through 2026-04-17). Same code, same data, no
network variables — a cleaner divergence measurement than production, but
NOT evidence about what production currently serves.

## Amendment-2 sweep results (which duplicate is WRONG, not just unused)

| Cluster | Verdict | Detail |
|---|---|---|
| accuracy (3 endpoints) | **DIVERGE** | `/api/predict/accuracy` = **9.5%** accuracy (147 resolved, source: simulations); `/api/predictions/accuracy` = **53.5%** (71 resolved, source: reasoning_predictions incl. partial credit); `/api/accuracy/summary` = **31.0%** (71 resolved, strict). Three published "accuracies" for the same system differ by 5.6×. |
| calibration (2 endpoints) | **DIVERGE** | sample size 40 vs 147 — different tables AND different windowing; bin constructions not even comparable. |
| history (2 endpoints) | AGREE | same rows surface despite different source tables. |
| backtest (2 endpoints) | NOT-COMPARABLE | different populations by design; `/api/backtest/runs` carries no metrics. |

## Stage 2b byte-match (scripts are the authority; endpoints are the suspect)

| Family | Exit | Mismatched fields |
|---|---|---|
| accuracy summary | **0 — clean** | 0 |
| track record | 1 | 39 (all in the Brier/reliability/ECE/Murphy sub-family, e.g. ECE recomputed 0.316 vs endpoint 0.174) |
| calibration | 1 | 61 (same scoring sub-family) |
| validation summary | 1 | 7 (endpoint reports 9 validated rows; reconstruction from `prediction_log` finds 0 in-window — endpoint reads a different population) |

Reading, per the verify README's direction-of-authority rule: the hit-rate /
Wilson layer reconstructs cleanly; the SCORING layer (reliability bins, ECE,
Murphy) published by the endpoints does not match an independent
reconstruction from raw rows, and the validation summary counts a population
the reconstruction cannot find. Next action (Stage 2b lane, not this
directive): check each script against the spec, then treat the endpoint as
the suspect — either endpoint math or an undocumented row filter is wrong.

## Consequences fed into Stage 2a dedup

1. The accuracy cluster's 9.5%-vs-53.5%-vs-31.0% spread is exactly the
   "which duplicate was wrong" evidence amendment 2 wanted before deleting
   any of the three. The dedup decision now has numbers.
2. Anything CITING an accuracy number (dashboards, README, investor-facing
   copy) must name its endpoint until dedup lands — the numbers are not
   interchangeable.
3. DNS/andon: `asx.marketoracle.ai` (and `staging.`) no longer resolve; the
   apex does. Either the domain records lapsed or the deployment moved.
   Stage 2a's access-log window CANNOT START until a reachable production
   host is confirmed — and if production has genuinely been dark, the
   window's zero-traffic evidence is trivially satisfied but must be
   confirmed from the Railway dashboard (owner action, not agent-checkable).
