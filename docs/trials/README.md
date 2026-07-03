# Trials register

The multiplicity ledger (López de Prado / Deflated-Sharpe discipline, adopted
via `docs/extraction-table.md`): every configuration, prompt, threshold, or
analysis-protocol variant EVALUATED gets an entry here — kept or discarded.
The expected best result of N zero-skill trials grows with N, so a result is
only interpretable next to the number of attempts behind it. Every published
metric page must cite its trial count from this register.

## Rules

1. **Append before running.** Register the trial (result `pending`) before
   the experiment executes; append a follow-up entry with the outcome.
   Post-hoc registration defeats the purpose.
2. **Never edit, only append.** Entries are hash-chained
   (`entry_hash = sha256(prev_hash + canonical_entry_json)`); any edit breaks
   the chain and `scripts/verify/verify_trials_register.py` reports the line.
3. **Backfilled entries** (`source: backfilled`) reconstruct pre-register
   history from git; each cites its introducing commit in `git_ref`. They are
   marked because they cannot prove completeness — see epoch note below.
4. Append with:
   `python backend/scripts/append_trial.py --description ... --config ... --metric ... [--result ...]`
5. Verify with:
   `python backend/scripts/verify/verify_trials_register.py`

## Epoch note (honesty boundary)

The register opened 2026-07-03 with 12 backfilled entries reconstructed from
git history. **Trials before that date are undercounted by an unknown
amount** — informal prompt/threshold iterations left no durable record.
Consequently any multiplicity correction (Deflated Sharpe, PBO) computed over
pre-epoch work uses a LOWER BOUND on N and must say so. Post-epoch, an
experiment absent from this register cannot be cited in any published claim.
