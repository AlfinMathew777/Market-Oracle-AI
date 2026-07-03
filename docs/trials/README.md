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

## External anchoring (OpenTimestamps)

Register heads are anchored to Bitcoin via OpenTimestamps: a head-attestation
file in `anchors/` records the chain head hash (which commits to every entry
under it), and its `.ots` proof is created by
`python backend/scripts/anchor_ots.py anchors/<head-file>.txt`. Fresh proofs
carry pending calendar attestations; upgrade to a Bitcoin-confirmed proof
later with `ots upgrade` (hours). Verification of proofs is Stage 2c scope
(rfc-worldclass §5 amendment 1). Anchor after appending pre-registration
entries — the point is that thresholds provably predate the data.

**Dependency justification (constraint 6):** `opentimestamps-client` (and its
`opentimestamps` library) — required because RFC-3161/OTS server-side proof
is amendment 1's explicit mechanism and cannot be reimplemented credibly
in-house (the trust comes from the public calendar/Bitcoin infrastructure).
Dev-only dependency: used by `anchor_ots.py` at anchoring time, never
imported by backend runtime code. Known limitation: the stock `ots` CLI is
broken on Windows (python-bitcoinlib OpenSSL 1.x ctypes load); the committed
script drives the library's calendar path directly, which does not touch the
broken code.

## Epoch note (honesty boundary)

The register opened 2026-07-03 with 12 backfilled entries reconstructed from
git history. **Trials before that date are undercounted by an unknown
amount** — informal prompt/threshold iterations left no durable record.
Consequently any multiplicity correction (Deflated Sharpe, PBO) computed over
pre-epoch work uses a LOWER BOUND on N and must say so. Post-epoch, an
experiment absent from this register cannot be cited in any published claim.
