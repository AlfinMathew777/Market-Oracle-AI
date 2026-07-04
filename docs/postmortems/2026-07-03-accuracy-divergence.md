# Postmortem: three accuracy endpoints, three numbers (9.5% / 53.5% / 31.0%)

Status: CAUSES NAMED (this document satisfies the pre-deletion requirement
of Phase C ruling 2); fixes deferred to Stage 2a per ruling. Evidence:
`docs/analyses/2026-07-03-duplicate-endpoint-divergence.md` (sweep against a
locally-served copy of snapshot `e16532e`).

## Ruling being executed

Canonical accuracy endpoint = **`/api/accuracy/summary`** (the byte-match
survivor — the only family whose endpoint output matched the independent
Stage 2b reconstruction exactly). The other two are deprecated in Stage 2a,
AFTER this postmortem names why each number is what it is. A1–A5 endpoint
defects are fixed forward on the survivor only.

## Semantic cause of each number

**`/api/predict/accuracy` = 9.5% (14/147).**
Source: `simulations` table via `database.get_accuracy_stats`
(`database.py:454`). Three compounding semantics: (1) **24-hour horizon** —
outcomes set by `run_accuracy_checks` when `check_at` (≈24h) passes, a
different question than the 7-trading-day protocol; (2) **NEUTRAL-inclusive
denominator** — `total = CORRECT+INCORRECT+NEUTRAL` (27 NEUTRAL outcomes
count as failures-by-denominator); (3) strict CORRECT-only numerator. It is
not "the system is 9.5% accurate"; it is "14 of 147 simulations beat a 24h
strict-direction check, neutrals counted against." Directional-only it would
read 14/120 = 11.7% — still the harshest protocol of the three.

**`/api/predictions/accuracy` = 53.5% (38/71).**
Source: `prediction_log` via `database.get_detailed_accuracy_stats`
(`database.py:714`). Semantics: 7-trading-day protocol; directional-only
(`predicted_direction NOT IN ('neutral')`); quality filter
`confidence >= 0.05`; numerator = **stored `prediction_correct` flag** — the
column andon A2 documents as distrusted (though a recheck on this snapshot
found zero disagreements between the flag and a sign+deadband re-derivation).
Provenance nuance: on the pristine snapshot this endpoint computes
**54.8% (34/62)**; the sweep captured 38/71 because the locally-served
backend's boot-time resolver mutated the scratch copy during the run.
CORRECTED SCOPE (2026-07-04 A-series audit): the boot job touched **79
rows** — 23 genuinely pending rows newly resolved (horizon-dated, labels
valid per A6-pass) plus **56 already-resolved NEUTRAL rows silently
re-resolved and overwritten** (A9: `WHERE prediction_correct IS NULL`
re-matches resolved neutrals forever). All 79 are quarantined in the scratch
artifact with reason code `A7_STARTUP_SIDE_EFFECT_RESOLUTION`; production
was never touched; the pristine snapshot used by the analyses was never
mutated. See rfc-worldclass §5.4 (A6–A9).

**`/api/accuracy/summary` = 31.0% (22/71).**
Source: `reasoning_predictions` via `services/accuracy_tracker`
(protocol v3). Semantics: strict `outcome_status = 'CORRECT'` only, out of
71 resolved TP/SL-protocol predictions (22 CORRECT / 49 INCORRECT);
partial-credit outcomes (TP1-only touches, etc.) are NOT counted correct.
This is the population the Reasoning Synthesizer actually produced, scored
strictly — and the only endpoint whose math reconstructs byte-identically.

## Why they can never agree

Three different populations (simulations vs prediction_log vs
reasoning_predictions), three different horizons (24h vs 7 trading days vs
TP/SL windows), three different denominators (neutral-inclusive vs
directional-quality-filtered vs all-resolved), two different numerator
authorities (recomputed outcome vs stored flag vs status enum). No bug
reconciles them; only deprecation does.

## Dispositions (Stage 2a, gated on the DNS postmortem's window rule)

1. Deprecate `/api/predict/accuracy` and `/api/predictions/accuracy`
   (410-logging stubs through the access-log window, then delete).
2. Any surface citing an accuracy number cites `/api/accuracy/summary` and
   names protocol v3, until swarm metrics (track-record family) clear A1.
3. A1–A5 fixed forward on the survivor + track-record family only; paired
   before/after values logged for already-resolved predictions (per §5.2
   proposed disposition, now ruled).
4. The 24h-vs-7d "provisional vs authoritative" duality stays ONLY inside
   the reputation loop (where supersede handles it) — never again as two
   public accuracy numbers.
