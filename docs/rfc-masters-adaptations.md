# RFC: Masters Adaptations — Prediction Masters Directive, Phase C

Status: DRAFT — awaiting approval. NO implementation code in this phase.
Inputs: `docs/masters-dossier.md` (Phase A, approved),
`docs/extraction-table.md` (Phase B, accepted with corrections; §6 amendment
governs), analysis-lane evidence (`docs/analyses/2026-07-03-*.md`), trials
register (`docs/trials/register.jsonl`), primary-source re-verification
(this document, §0).

Scope: the top-3 PIPELINE adaptations as re-ranked after analysis evidence
(extraction table §6.9). All flags default OFF, fail-open (a failing
adaptation never blocks a signal), staging first, flight-readiness review
before any flag flip. Every numeric protocol constant in this RFC is
pre-registered in the trials register before first use.

---

## 0. Primary-source re-verification (hostile-auditor standard)

Every number this RFC leans on was re-checked against its primary source on
2026-07-03. Verified: M6 23.3% (38/163) beat the uniform-RPS benchmark and
31.08% beat the investment benchmark, accuracy–returns rank correlation
≈0.04 overall (arXiv:2310.13357 — nuance: r≈0.12 for the top 5%, peaking
≈0.7 for the top 20%); M4 12-of-17 combinations, winner +9.4% over Comb, no
pure-ML entry beat Comb (IJF S0169207019301128); Fortin et al. 2014 — spread
must be computed as √(mean ensemble variance), never mean of std-devs, with
finite-ensemble correction √((M+1)/M) (JHM-D-14-0008.1); split-conformal
quantile ⌈(n+1)(1−α)⌉/n with finite-sample guarantee 1−α ≤ coverage ≤
1−α+1/(n+1) (arXiv:2107.07511); ACI update α_{t+1}=α_t+γ(α−err_t) with
deterministic long-run coverage bound |avg err−α| ≤ (max{α₁,1−α₁}+γ)/(Tγ) —
long-run average only, NOT per-step conditional coverage (arXiv:2106.00170);
COVID Hub ensemble = per-quantile MEDIAN (mean for its first ~7 weeks), most
consistently accurate vs components (PNAS 2113561119).

CORRECTED this phase and propagated: fractional-Kelly variance phrasing
(Thorp 2006 §7.3: growth c(2−c), std-dev scales by c) — dossier §2.1
corrected by this reference; meta-labeling event arithmetic (Peduzzi 1996:
30–100 rarer-class events for 3–5 features, not 150–300 resolved) — register
seq 13.

---

## 1. Adaptation #1 — Ledger schema completion (`ENABLE_LEDGER_SCHEMA_V2`)

**Master / mechanism.** DeepMind GraphCast lesson (Lam et al. 2023, Science
adi2336): the verified dataset is the crown jewel; models on top are
replaceable. Operationalized: persist, per prediction, everything the other
mechanisms need and that is unrecoverable if unwritten.

**What is persisted (shadow fields, forward-only, no migration of old rows):**
1. per-agent votes `{agent_id, archetype, vote}` (unblocks archetype
   leaderboard, agreement matrix, H2/H7, believability weights)
2. per-class probability vector as published (unblocks conformal, CRPS-side
   scoring without reconstruction)
3. MC quantile set widened to 9 points (5/10/16/25/50/75/84/90/95)
   (unblocks CRPS + rank histogram; today only 5/16/84/95 exist)
4. versioned feature vector `{schema_version, features…}` (unblocks
   meta-labeling and the regime-shift alarm)

**Falsifiable claim (pre-registered).** With the flag ON in staging, within
30 predictions: (a) 100% of new rows carry all four field groups; (b)
per-agent votes reconcile exactly with the aggregate `agent_bullish/bearish/
neutral` counts on ≥99% of rows; (c) zero bytes change in any existing
endpoint response while the flag is ON (shadow-only property).

**Kill criterion.** Any replay-regression byte diff attributable to the
writer → revert same day. Reconciliation failures >1% of rows → flag OFF,
root-cause before retry. Payload size >20 KB/prediction sustained → redesign
(store archetype-level aggregation instead of raw 50 agents).

**Paired-logging plan.** Pure shadow persistence: new columns/JSON fields are
written alongside every existing write; NOTHING reads them in this phase.
Old and new pipelines are the same pipeline — the pair is (existing outputs,
new fields), compared by the replay regression on every PR.

**Verify-script plan.** `scripts/verify/verify_agent_votes.py` (stdlib only,
imports nothing from backend/): for each new-schema row, assert per-agent
vote counts sum to the stored aggregates, archetype labels come from the
frozen persona registry, the probability vector sums to 1±1e-9 and matches
the published direction/confidence pair under the documented mapping, and
quantiles are monotone. Exit contract identical to existing Stage 2b scripts.

**Why rank #1.** The availability audit proved the cost of delay is
unrecoverable comparison-N (`2026-07-03-archetype-vs-ensemble.md`): 147
simulations already lost. Every mechanism in Tier 1 that is currently
blocked, plus H2, waits on this.

---

## 2. Adaptation #2 — Benchmark-opponents package
(`ENABLE_CLIMATOLOGY_AGENT`, `ENABLE_BASELINE_AGENTS`)

**Masters / mechanisms.** M-competitions (permanent humiliating baselines;
M4/M6 numbers in §0); Tetlock outside-view/climatology prior; CLV adaptation
deferred (baseline-validation caveat, extraction row 9 — NOT in this
package).

**Strongest-opponent answer (directive §Phase C question).** The single
benchmark most threatening to the swarm's usefulness claim is the
**per-ticker climatology-prior agent**. Grounds: M6 — 76.7% of teams failed
to beat the uniform prior, and per-ticker base rates are strictly stronger
than uniform; the snapshot preview shows swarm Brier ≈0.65 vs uniform's
0.667 — near-zero margin, so climatology plausibly BEATS the swarm today.
It is added FIRST, per the directive ("the strongest possible opponent is
the point"). Publish-either-way is already pre-registered (rfc-worldclass §5
amendment 3a: BSS-vs-climatology thresholds at N=50 and N=150; register
seq 8).

**Two lanes (acceptance ruling §6.7).**
- **ANALYSIS lane (first, retroactive):** freeze baseline definitions in the
  trials register, THEN score them as-of each of the 124 resolved snapshot
  predictions. Strict as-of-date: climatology uses only rows resolved before
  the prediction's own timestamp; persistence/smoothing use only prior
  closes. Output: `docs/analyses/` report with BSS(swarm vs each baseline) +
  cluster-bootstrap CIs, segmented by resolution-protocol version (v1/v2/v3
  never pooled).
- **PIPELINE lane (flag-gated):** the same frozen definitions emit rows at
  prediction time into `prediction_log` tagged `source=baseline`, scored by
  the identical machinery, shown on the honesty dashboard beside the swarm.

**Frozen baseline definitions (pre-registered in the register before the
retroactive run; versions bump only by new register entry):**
- `climatology_v1`: per-ticker class frequencies over all prior-resolved
  same-protocol rows; Laplace +1 smoothing; NEVER pooled across tickers;
  emits the frequency vector as its forecast.
- `persistence_v1` (naive): predicted class = actual class of the ticker's
  most recent resolved same-horizon window; confidence = that class's
  climatological frequency.
- `smoothing_v1`: exponential smoothing (α=0.3, pre-registered) over the
  ticker's daily return series, mapped to 3-class by the same ±0.5% deadband.
- `uniform` (constant ⅓,⅓,⅓ — already the BSS reference; kept as an agent
  so it appears on the same leaderboard).
- seasonal-naive: EXCLUDED at definition time (register entry with reason:
  no credible weekly seasonality in daily ASX direction; its M-comp role is
  covered by persistence). Kill-criterion collapse rule (score-series
  correlation >0.98 with a simpler baseline) armed for the rest.

**Falsifiable claim (pre-registered, publish-either-way).** At N=50 and
N=150 same-protocol resolved predictions: BSS(swarm vs climatology_v1) with
cluster-bootstrap 95% CI. Pre-committed sentences: CI>0 — "the swarm adds
skill over its own base rates"; CI straddles 0 — "no detectable skill over
base rates yet"; CI<0 — "the swarm is currently worse than its own base
rates." Whichever sentence is true is published unedited.

**Kill criteria.** Baseline not byte-reconstructable as-of any date by the
verify script → that baseline is unpublished until fixed (a broken opponent
is worse than none). Collapse rule as above. The SET of baselines is
permanent by mandate (M-comp lesson) — individual definitions version, the
opposition never disappears.

**Paired-logging plan.** Baseline rows never gate, veto, or modify swarm
signals (fail-open: baseline computation failure logs a warning, swarm
proceeds). Rows carry `source` + `baseline_version` so every comparison
names its opponent version. Pipeline-lane rows land beside swarm rows for
the same question id — the pair is (swarm row, baseline rows) per question.

**Verify-script plan.** `scripts/verify/verify_benchmarks.py`: recomputes
every baseline forecast from raw OHLC + ledger rows as-of the prediction
timestamp and byte-compares against stored baseline rows (float tol 1e-6);
recomputes the BSS table the dashboard publishes. Stdlib+numpy only, imports
nothing from backend/.

---

## 3. Adaptation #3 — Conformal sets + ACI (`ENABLE_CONFORMAL_SETS`)

**Masters / mechanism.** Vovk et al.; Angelopoulos & Bates 2021; Gibbs &
Candès 2021 (formulas re-verified, §0). Published prediction SETS over
{bullish, bearish, neutral} at α=0.10 beside the capped confidence.

**Protocol (all constants pre-registered).** Nonconformity score = 1 −
forecast probability of the realized class, where the forecast vector is the
documented direction+confidence mapping (reconstructable for ALL existing
rows; read from the persisted probability vector once Adaptation #1 lands).
Split-conformal quantile ⌈(n+1)(1−α)⌉/n over the trailing same-protocol
calibration window; deployed as ACI with γ=0.005 (pre-registered; sets
α₁=0.10), err_t evaluated at each resolution in ledger order. Sets are
PUBLISHED ONLY — they never gate signals, never alter confidence, and the
85% cap is untouched.

**Falsifiable claim (pre-registered).** Honest two-part claim, matching what
the theorems actually give: (a) THEOREM (not measured): long-run average
coverage converges to 90% by Gibbs–Candès Prop 4.1 — published with the
bound, labeled as a guarantee about the long-run average, explicitly NOT
per-prediction conditional coverage; (b) MEASURED: rolling-60-resolution
empirical coverage stays within ±5 points of 90% and mean set size < 3
(a permanently-full set achieves coverage vacuously — set size is the
sharpness metric, reported beside coverage, Forecast-Hub style).

**Kill criterion.** Rolling coverage outside ±5 points for 2 consecutive
months → implementation bug by construction (ACI cannot drift long-run) →
unpublish sets pending fix. Mean set size ≥ 2.8 sustained for a quarter →
sets are uninformative at current skill; keep computing, stop featuring on
the public dashboard (register entry either way).

**Paired-logging plan.** For every prediction, the conformal set is logged
next to the existing confidence field (pair = hand-tuned confidence vs
distribution-free set). Nothing consumes the sets in-pipeline; the dashboard
reads them only when the flag is ON. ACI state (current α_t) is persisted
per update so replay reproduces the exact sequence deterministically.

**Verify-script plan.** `scripts/verify/verify_conformal.py`: re-walks the
resolved ledger in order, recomputes nonconformity scores, the split
quantile, and every ACI α-update from α₁ and γ, and byte-compares the
resulting set sequence + published coverage numbers against stored values.
Deterministic by construction — no model, no randomness.

---

## 4. Order of work and gates

1. **Retroactive benchmark ANALYSIS** (no flag, no pipeline code): register
   entries freezing definitions → as-of scoring over the snapshot → publish
   analysis doc. Runnable immediately on approval; loses nothing to the
   Stage 2c queue hold.
2. **Adaptation #1** (schema) — Phase D implements this FIRST; smallest
   surface, unblocks the most, and its kill criterion is a pure replay
   regression.
3. **Adaptation #2 pipeline lane** behind its flags, staging only.
4. **Adaptation #3** after #1's probability-vector persistence (interim
   reconstruction path allowed for the retroactive calibration set).

Every step lands behind the Architect Directive gates: flags OFF by default,
fail-open, one logical change per commit, replay regression green,
flight-readiness review before any staging flag flip, and a trials-register
entry before any evaluation run.

**STOP — Phase C ends here. No implementation code has been written for any
adaptation. Phase D (implement rank #1 only — the schema completion) awaits
approval.**
