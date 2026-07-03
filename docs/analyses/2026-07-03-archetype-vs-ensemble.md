# Per-archetype vs median-ensemble comparison

Status: **BLOCKED — required data was never persisted** · Audit script:
`backend/scripts/analyses/agent_vote_availability.py` · 2026-07-03

## What was ordered

The Forecast-Hub mechanism (extraction table row 5): score each archetype's
resolved predictions against the equal-weight median ensemble of all
archetypes, publish whichever way it goes.

## Why it cannot run on any existing data

Audit of the production snapshot (commit `e16532e`, rows through 2026-04-17):

| Surface | Finding |
|---|---|
| `simulations.agent_votes` | non-NULL in 147/147 rows but an **empty JSON list in all 147** |
| rows with per-agent identity (persona/archetype/agent_id) | **0** |
| `simulations.full_json` (20 rows) | `agent_consensus` = aggregate counts only (`{"up": 5, "down": 6, "neutral": 14}`) |
| `reasoning_predictions.agent_consensus` (75 rows) | aggregate counts + strength score only |

Aggregate vote counts cannot be decomposed into per-archetype forecasts.
No persisted surface records WHICH persona voted WHAT. The comparison is
therefore impossible for every prediction made to date — this comparison-N
is permanently lost.

## Standing conclusions

1. **Schema prerequisite promoted to hard requirement:** the pipeline must
   persist per-agent votes `{agent_id, archetype, vote, weight}` per
   simulation before ANY per-archetype mechanism (leaderboard, correlation
   audit, believability weights, H2) can ever be evidenced. This is the
   cheapest possible fix with the highest option value — it should ride the
   first pipeline PR of Phase D.
2. `agent_votes` being a permanently-empty column is also a Stage 2a-style
   requirement-with-no-owner: something writes `[]` on every row. The write
   site should either persist real votes or the column should be removed —
   an empty-but-always-written column is worse than either.
3. Retroactivity note (per the Phase B corrections): unlike the benchmark
   opponents — which CAN be scored retroactively because their inputs
   (prices, base rates) are reconstructable as-of-date — per-archetype
   history is unrecoverable. Every week without the schema fix loses
   comparison-N that can never be backfilled.
