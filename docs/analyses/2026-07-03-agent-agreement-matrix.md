# Pairwise agent-agreement matrix

Status: **BLOCKED — same persistence gap as the archetype comparison** ·
Audit script: `backend/scripts/analyses/agent_vote_availability.py` · 2026-07-03

## What was ordered

The WorldQuant mechanism (extraction table row 7): pairwise agreement between
agents/personas across predictions, an effective-ensemble-size statistic, and
the H2 prerequisite measurement ("40 agents that always agree are one agent").

## Why it cannot run

Identical root cause to `2026-07-03-archetype-vs-ensemble.md`, same audit
numbers: `simulations.agent_votes` is an empty list in 147/147 rows and no
persisted surface carries per-agent identity. A pairwise matrix needs
per-agent votes per prediction; aggregate (bullish, bearish, neutral) counts
admit no pairwise decomposition.

## What the aggregate data DOES already say (weak substitute, on record)

From the spread–error analysis on the same snapshot: normalized vote-entropy
spans only 0.69–0.99 across 107 predictions — the swarm is highly split on
essentially every question, never near-unanimous. That is consistent with
either (a) genuinely diverse personas or (b) shared-model noise around a
common uncertain answer. Distinguishing (a) from (b) is EXACTLY what this
matrix is for, and is the empirical fork on which extremizing (rejection R1)
and believability weights (H2/H7) both hang. The aggregate data cannot
resolve it.

## Standing conclusions

1. Same schema prerequisite as the archetype comparison: persist
   `{agent_id, archetype, vote}` per simulation. One fix unblocks both
   analyses plus H2/H7.
2. Until the matrix exists, all "50-agent diversity" language stays
   unsubstantiated — the honest public phrasing is "50 sampled votes,"
   not "50 independent perspectives."
3. Unrecoverable retroactively; every unfixed week loses comparison-N.
