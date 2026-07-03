# Spread–error calibration — does swarm disagreement predict miss size?

Status: EXECUTED 2026-07-03 · Verdict: **NULL RESULT (provisional, N below
pre-registered threshold)** · Script: `backend/scripts/analyses/spread_error.py`

## Provenance

- Data: last git-tracked production DB snapshot, commit `e16532e`
  (extract: `git show 'bbf5a25~1:backend/aussieintel.db'`), rows through
  2026-04-17.
- The live track-record endpoint was unreachable at run time —
  `asx.marketoracle.ai` no longer resolves in DNS (andon finding, logged in
  the Stage 2a/2b status). Live N is therefore UNKNOWN; snapshot N is a
  lower bound.
- Method pre-registered in `docs/extraction-table.md` row 2 (ECMWF
  spread–error mechanism). Seed 42, 10k cluster-bootstrap draws, ±0.5%
  deadband, forecast vector per `trust/scoring.py` spec (independently
  duplicated).

## Sample

107 resolved `prediction_log` rows with agent vote counts — ALL protocol v2
(7-trading-day resolution notes); the 23 v1 rows carry no vote counts, so the
protocol segments coincide. Critically, the 107 rows collapse into only
**19 independent resolution clusters** (identical ticker + entry + exit):
repeated predictions into the same outcome window. Cluster bootstrap is used
for CIs; effective sample is 19, not 107.

## Result

Dispersion = normalized entropy of (bullish, bearish, neutral) vote counts.

| Tercile | n | dispersion range | Brier | 95% CI (cluster bootstrap) |
|---|---|---|---|---|
| low | 35 | 0.693–0.874 | 0.664 | [0.500, 0.833] |
| mid | 36 | 0.874–0.906 | 0.629 | [0.548, 0.802] |
| high | 36 | 0.906–0.988 | 0.694 | [0.500, 0.999] |

Spearman(dispersion, Brier) = **−0.03**. All tercile CIs overlap almost
completely. No monotonic spread→error relationship is detectable.

Two aggravating observations:

1. **The swarm is almost never in agreement.** Dispersion spans only
   0.69–0.99 of the possible 0–1 range — the ensemble is highly split on
   essentially every prediction, so there is little spread VARIATION for the
   diagnostic to work with. This is consistent with the H2 concern (agents
   share one base model and cluster around a common uncertain answer).
2. **Mean Brier ≈ 0.65 vs the uniform-forecast reference 0.667** — on this
   snapshot the swarm's probabilistic skill over these rows is barely above
   uniform. (BSS vs climatology is pre-registered 2c scope; not computed
   here.)

## Verdict against the pre-registered kill criterion

The extraction-table criterion ("terciles indistinguishable at N≥150 →
publish the null, forbid spread-conditioned confidence logic") is NOT yet
triggered: N=107 (19 clusters) < 150. Standing conclusions:

- **Publish this null as-is** (this document).
- **No spread-conditioned confidence logic may ship** while the null stands.
- The pipeline version of this diagnostic (`ENABLE_SPREAD_ERROR_PAGE`)
  remains a candidate ONLY as a monitoring page; its Phase C priority is
  DOWNGRADED — the snapshot suggests the swarm lacks the dispersion
  variation the mechanism needs (precondition partially failed, in the
  directive's terms).
- Re-run at N≥150 resolved-with-votes and ≥50 independent clusters; the
  cluster count, not the row count, is the binding sample size.
