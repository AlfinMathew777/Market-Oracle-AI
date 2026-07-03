# Reputation provenance audit — can the values be rebuilt from evidence alone?

Status: EXECUTED 2026-07-03 (Phase C ruling 4) · Verdict: **FEYNMAN-TEST
FAILURE recorded for the reputation/believability metric family** —
rebuildability is designed-for but undemonstrated and currently unverifiable.
Consequence: **believability experiments frozen** until schema v2 accumulates
data and a reconstruction script exists.

## What the audit asked

Can `source_reputation` / `agent_reputation` values (the inputs to
believability weighting) be rebuilt from persisted evidence alone — without
trusting the reputation tables themselves?

## What the code persists (design review)

The update path is `outcome_checker` → `update_from_resolution` →
`ledger.find_attribution(simulation_id)` → `apply_outcome` → EMA steps:

- **Attribution IS persisted** in the hash-chained trust ledger at
  certification time: `archetype_votes` (4-role counts per side — dissent
  included), `sources`, `trend_label`, `chain_override`
  (`trust/attribution.py:145`). Note this is ARCHETYPE-level; per-agent
  votes remain unpersisted (separate finding, schema v2).
- **Resolutions ARE persisted** (`prediction_log`: outcome, change_pct,
  resolved_at) and the update rule is deterministic given order — EMA with
  BASE_ALPHA=0.08, margin damping, regime collapse, provisional→
  authoritative supersede backed out via the `reputation_contribution`
  audit-trail table (`trust/reputation.py:96-108`).
- Legacy-payload replay compatibility was deliberately preserved when
  dissent-learning shipped (`reputation_update.py:138-151`) — the design
  intends replayability.

## Why the verdict is still FAILURE

1. **No reconstruction script exists.** The Stage 2b scope (`rfc-worldclass
   §5.1`) covers track-record/calibration/accuracy/validation/backtest;
   reputation was never in scope. Designed-for-replay without a
   `scripts/verify/verify_reputation.py` is exactly the gap the Feynman
   standard rejects: provable ≠ proved.
2. **No accessible evidence to test against.** The reputation tables were
   introduced after the last tracked DB snapshot (2026-04-17 predates the
   trust stack); the only DB that contains reputation state is on the
   unreachable production host (DNS postmortem). Zero rows of
   attribution-bearing ledger evidence can be inspected from here.
3. **Order dependence with a self-referential crutch.** EMA + supersede
   makes values order-dependent. Ordering is recoverable from `resolved_at`
   plus stage, but ties and retro-edits would need `reputation_contribution`
   — a table owned by the same subsystem and NOT hash-chained, so using it
   as rebuild input is partially circular.

## Consequences (per ruling)

- Feynman-test failure recorded for the reputation/believability family —
  it joins the §1.7 gap list until a reconstruction script exists AND has
  been run against real ledger evidence.
- **`USE_BELIEVABILITY_WEIGHTS` stays OFF and all believability/H2/H7
  experiments are frozen** until (a) schema v2 persists per-agent votes and
  per-prediction probability vectors, (b) `verify_reputation.py` exists
  (stdlib-only, replays ledger attributions + resolutions into values and
  byte-compares against the store), and (c) the replay has been executed
  against a reachable DB. Recovery path is concrete; the freeze is
  evidence-gated, not indefinite.
- The anchored pre-registration for the paired believability analysis
  (rfc-worldclass §5 amendment 3b) is unaffected — it anchors BEFORE any
  flag flip, and this audit is precisely why that ordering was right.
