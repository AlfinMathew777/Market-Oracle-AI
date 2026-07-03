# Retroactive flat-vs-quarter-Kelly paper-P&L recompute

Status: EXECUTED 2026-07-03 · Verdict: **NO GROWTH EDGE EITHER WAY; KELLY
CUTS DRAWDOWN ~65%** · Script: `backend/scripts/analyses/kelly_recompute.py`

## Provenance

- Data: git-tracked production DB snapshot, commit `e16532e` (rows through
  2026-04-17); live endpoint unreachable (see spread–error report).
- Formulas duplicated from `services/position_sizer.py` on purpose
  (independence rule): quarter-Kelly (0.25), shrinkage constant K=20 toward
  the breakeven win rate, no-edge → zero stake. Walk-forward, strictly
  as-of-date: each stake uses only predictions resolved before its own
  `predicted_at`. No look-ahead.
- Flat comparator: constant 5% of bankroll per position. Neutral predictions
  take no position under either strategy.

## Sample

68 directional (non-neutral) resolved predictions; realized directional win
rate 54.4%. Same clustering caveat as the spread–error analysis: many rows
share identical resolution windows, so the independent-bet count is far
lower than 68.

## Result

| Mode | Kelly non-zero stakes | Flat final bankroll | Kelly final bankroll | Flat max DD | Kelly max DD |
|---|---|---|---|---|---|
| per-ticker history (faithful to position_sizer) | 37/68 | 1.0041 | 1.0033 | 4.09% | **1.42%** |
| pooled history (secondary) | 42/68 | 1.0041 | 0.9974 | 4.09% | 1.49% |

## Reading

1. **Growth: indistinguishable.** +0.41% (flat) vs +0.33% (quarter-Kelly,
   per-ticker) over the whole snapshot — noise at this N. The honest
   sentence for the dashboard: "there is not yet ledger evidence that
   quarter-Kelly sizing beats flat sizing on growth."
2. **Risk: Kelly does its actual job.** Max drawdown 1.42% vs 4.09% —
   the shrinkage prior kept 31 of 68 positions at ZERO stake (no measured
   edge → no bet), which is Thorp's rule working as designed, not a defect.
3. The extraction table's Kelly row (ADOPTED) gains its missing evidence
   line: sizing responds to the track record and suppresses unmeasured-edge
   bets; superiority on growth is UNPROVEN and must not be claimed.

## Standing conclusions

- Keep quarter-Kelly as the paper-position sizer (risk case, not growth
  case). Re-run this recompute at each quarterly review; the growth claim
  stays banned until a CI excludes zero.
- Assumptions that bound this result: 5% flat comparator, 25% stake cap,
  payoff ratio from realized prior wins/losses (default 1.0 with no
  history). All are printed by the script for reproduction.
