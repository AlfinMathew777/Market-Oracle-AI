# Extraction Table — Prediction Masters Directive, Phase B

Status: ACCEPTED WITH CORRECTIONS 2026-07-03 — see §6 amendment (evidence
from the executed analysis lane, resolved-N statement, re-ranking, TSFM
ruling, benchmark split). §§1–5 preserved as accepted; where §6 contradicts
an earlier row, §6 governs.

**Resolved N (stated per acceptance ruling):** live endpoint UNREACHABLE
(`asx.marketoracle.ai` NXDOMAIN, 2026-07-03 — andon). Last git-tracked
production snapshot (commit `e16532e`, rows through 2026-04-17):
`prediction_log` **124 resolved** of 147 (107 carry AGGREGATE vote counts —
the three integers `agent_bullish/agent_bearish/agent_neutral`; **19
independent resolution clusters**, 68 directional); `reasoning_predictions`
**71 resolved** of 75. Reconciliation (Phase C ruling 3): "107 with votes"
and "agent_votes empty in 147/147" describe DIFFERENT fields — the
per-agent vote LIST column `simulations.agent_votes` is an empty JSON array
in all 147 rows (no per-agent identity persisted anywhere), while the
aggregate per-class COUNTS in `prediction_log` exist on 107 resolved rows.
Aggregates power the spread–error analysis; the empty per-agent lists are
what blocks the archetype/agreement analyses and motivate schema v2. By resolution protocol: **v1** (pre-deadband-notes,
23 rows, no vote counts) · **v2** (7-trading-day entry/exit protocol, 101
rows) · **v3** (`reasoning_predictions` TP/SL protocol, 71 rows — scored on
a different definition; never pool with v1/v2). Live N is unknown until a
reachable host is confirmed; snapshot numbers are lower bounds.
Input: `docs/masters-dossier.md` (Phase A, approved). Every row below passed
the §3 protocol: explicit precondition check, no dependence on data/capital/
speed MO lacks, preference for ledger-scored replayable code over prose, and
the adoption test (must strengthen adversarial trust, public honesty, or
auditability — accuracy alone does not qualify).

Pillar codes: **AT** adversarial trust · **PH** public honesty · **AU** auditability.

---

## 0. Precondition verification (closing Phase A's open gaps)

Verified in code this phase:

1. **MC distributions: PARTIAL.** Raw MC samples are not persisted.
   `simulations.full_json` carries the 5/16/84/95 percentiles
   (`services/game_theory/monte_carlo.py:287-290`) and the stability score
   (extracted by `monitoring/alerts.py:324`). Consequence: interval scoring
   (WIS at two central intervals + median) is computable on EXISTING rows;
   proper CRPS needs a wider persisted quantile set — a small, forward-only
   schema addition inside `full_json` (no migration).
2. **Feature vectors: PARTIAL.** `prediction_log` persists market snapshot
   (iron ore, AUDUSD, Brent, price), agent vote counts, `trend_label`,
   confidence (`database.py:110-144`); `reasoning_predictions` persists
   `event_classification`, `market_context`, `agent_consensus` as JSON.
   Enough for a MINIMAL adversarial-validation and meta-labeling feature set;
   a richer, versioned feature schema is a cheap forward-only addition.
3. **Kelly sizing: ALREADY IMPLEMENTED.** `services/position_sizer.py` is
   quarter-Kelly (`DEFAULT_KELLY_FRACTION = 0.25`) with a shrinkage prior —
   win rate shrunk toward no-edge until ~20 resolved predictions, "no
   historical edge → no position." Thorp's mechanism (dossier §2.1) is
   therefore ADOPTED, not pending; the row below records the retroactive
   precondition check for the definition-of-done audit.
4. **Resolved-ledger N: UNKNOWN from local checkout** — production DB only
   (local `prediction_log` is empty; see project memory). Every N-gated row
   below states its minimum N; Phase C must read the real N from
   `/api/accuracy/track-record` before ordering implementation.

---

## 1. Rubric

Per the Architect Directive, each mechanism is scored 0–2 on five axes
(total /10): **N** compounds with ledger growth · **U** unfakeable (survives a
hostile auditor; reconstructable by `scripts/verify/`) · **C** complexity cost
INVERTED (2 = trivial, 0 = heavy/replay-threatening) · **D** deletion
potential (lets us delete or replace existing surface) · **T** thesis
alignment (identity pillars, surpass axes).

| # | Mechanism | Master | N | U | C | D | T | Total |
|---|---|---|---|---|---|---|---|---|
| 1 | Baseline benchmark agents | M-comps | 2 | 2 | 2 | 1 | 2 | **9** |
| 2 | Spread–error calibration | ECMWF | 2 | 2 | 2 | 1 | 2 | **9** |
| 3 | Climatology-prior agent | Tetlock/M-comps | 2 | 2 | 2 | 1 | 2 | **9** |
| 4 | Trials register | López de Prado | 2 | 2 | 2 | 0 | 2 | **8** |
| 5 | Archetype-vs-ensemble leaderboard | Forecast Hub | 2 | 2 | 2 | 0 | 2 | **8** |
| 6 | Triple-barrier resolution | López de Prado | 2 | 2 | 1 | 1 | 2 | **8** |
| 7 | Agent correlation audit | WorldQuant | 1 | 2 | 2 | 2 | 1 | **8** |
| 8 | Conformal sets + ACI | Vovk/Gibbs–Candès | 2 | 2 | 1 | 0 | 2 | **7** |
| 9 | Market-relative skill score | Syndicates/CLV | 2 | 1 | 2 | 0 | 2 | **7** |
| 10 | Quantile scoring (WIS→CRPS) | ECMWF/Hub | 2 | 2 | 1 | 0 | 2 | **7** |
| 11 | Mechanism-class attribution | AQR | 2 | 1 | 2 | 0 | 2 | **7** |
| 12 | TSFM benchmark agent | Chronos et al. | 1 | 2 | 1 | 0 | 2 | **6** |
| 13 | Meta-labeling | López de Prado | 2 | 1 | 0 | 1 | 2 | **6** |
| 14 | DSR + PBO reporting | López de Prado | 1 | 2 | 1 | 0 | 2 | **6** |
| 15 | Regime-shift alarm | Kaggle | 1 | 1 | 1 | 0 | 2 | **5** |
| 16 | Loss-scenario gate | Renaissance | 1 | 1 | 2 | 0 | 1 | **5** |
| 17 | Sector bias correction | ECMWF | 2 | 1 | 1 | 0 | 1 | **5** |
| — | Kelly sizing | Thorp | — | — | — | — | — | ADOPTED |

Scoring notes: #7's D=2 is the table's only pruning mechanism (redundant
agents get deleted). #13's C=0 reflects that a trained artifact threatens
byte-identical replay unless model versions are pinned and hashed into the
ledger. #9's U=1 is the CLV caveat — a self-built baseline can be gamed by
mis-specification; freezing + versioning is the mitigation, not a cure.

---

## 2. Extraction table (§3 format, ranked by rubric)

### Tier 1 — precondition met today, data already in the ledger

| Mechanism | Why it works there | Precondition | MO meets it? | Concrete small adaptation | Pillar | Kill criterion | Flag |
|---|---|---|---|---|---|---|---|
| **1. Baseline benchmark agents** (naive, seasonal-naive, exp-smoothing) | M4: combinations of simple methods beat complex ones; M6: 77% of teams lost to the uniform baseline. Baselines convert "sophisticated" into one falsifiable number | Baselines answer the SAME pre-registered questions as the swarm, scored by the same ledger, never removed | YES — pure engineering; scoring harness live in `trust/scoring.py` | Three deterministic baseline "agents" emit direction+confidence per simulation; rows land in `prediction_log` tagged `source=baseline`; published beside swarm BSS | AT, PH | A baseline whose score series correlates >0.98 with a simpler baseline is collapsed into it (mis-specified, adds nothing). The SET is permanent by mandate | `ENABLE_BASELINE_AGENTS` |
| **2. Spread–error calibration** | ECMWF: a reliable ensemble's spread predicts error magnitude; verified via spread-vs-RMSE and rank histograms | Per-prediction dispersion + resolved outcomes | YES TODAY — vote counts in `prediction_log`, outcomes resolved | Verify-script + honesty-dashboard page: bin resolved ledger by vote-spread terciles, Brier + bootstrap CI per bin. Answers "does 50-agent disagreement mean anything?" | PH, AT | If at N≥150 the tercile Brier CIs fully overlap (spread uninformative), publish the null, forbid any spread-conditioned confidence logic, archive the page after one more cycle | `ENABLE_SPREAD_ERROR_PAGE` |
| **3. Climatology-prior agent** | Tetlock: outside view first — base rates before stories; M-comps: climatology embarrasses complex systems | Per-ticker base rates from resolved history; NEVER pooled across tickers (directive §6.3) | YES — `climatology_probs()` exists in `trust/scoring.py`; needs per-ticker grouping + agent wrapper | A benchmark agent forecasting each ticker's own historical class frequencies; every archetype's BSS is reported RELATIVE to it | AT, PH | If its forecast cannot be byte-reconstructed from the ledger by `scripts/verify/`, or any code path pools tickers, feature is reverted same-day | `ENABLE_CLIMATOLOGY_AGENT` |
| **4. Trials register** | López de Prado: expected best Sharpe of N zero-skill trials grows √(2·ln N); unknown N makes every backtest number meaningless. Cannot be retrofitted | Append-only log of every config/prompt/threshold variant evaluated, from now on | YES — discipline + a small table; hash-chain machinery exists in `trust/ledger.py` | `trials` table (hash-chained like the ledger): config hash, hypothesis, date, outcome metric, kept/discarded. Every future BSS/backtest publishes its trial count beside it | PH, AU | If an audit finds ≥2 experiments run without register entries, the register is publicly declared unreliable and its numbers unpublished until remediated — an incomplete register is false assurance, worse than none | `ENABLE_TRIALS_REGISTER` |
| **5. Archetype-vs-ensemble leaderboard** | COVID Forecast Hub: the equal-weight median ensemble beat essentially every component model consistently; individual models were erratic | Per-archetype forecasts stored per question; equal-weight median computed the same way every time | YES — `agent_votes` JSON in `simulations`; archetype attribution live in `trust/attribution.py` | Published page: per-archetype Brier/BSS vs the median-of-archetypes ensemble, updated per resolution, whichever way it goes | PH, AT | Ranks are hidden (shown as "insufficient N") for any archetype with <30 resolved predictions — publishing small-N ranks is Goodhart bait | `ENABLE_ARCHETYPE_LEADERBOARD` |
| **6. Triple-barrier resolution** | López de Prado: fixed-horizon labels ignore volatility (same +1% is noise for a miner, signal for a utility) and path (intra-horizon stop-outs count as wins) | Daily OHLC + per-ticker EWMA vol; barriers pre-registered per prediction at creation time | YES — yfinance OHLC pipeline exists; EWMA is ~10 lines | Pre-register upper/lower barriers at p₀·(1±k·σₜ) + vertical barrier alongside each prediction; resolve by first touch; run PAIRED with fixed-horizon labels (paired logging), compare | AU, AT | If barrier and fixed-horizon labels disagree on <5% of predictions after 100 resolutions, the added complexity isn't paying — revert to fixed-horizon | `ENABLE_TRIPLE_BARRIER_LABELS` |
| **7. Agent correlation audit** | WorldQuant: portfolio power comes from decorrelated signals (mean pairwise alpha correlation ~16%); 40 agents that always agree are one agent | Per-agent vote history per simulation | YES — `agent_votes` JSON persisted | Pairwise agreement matrix across personas, published; effective-ensemble-size statistic on the honesty dashboard. THE prerequisite measurement for H2 | AT, PH | Two-sided: if agreement ≈ 1 (swarm is one agent), publish that and freeze all "diversity" claims; if pruning is attempted, it must show ledger-scored BSS improvement within one quarter or the pruning tool is deleted | `ENABLE_AGENT_CORRELATION_AUDIT` |
| **9. Market-relative skill score** | Syndicates: beating the sharpest market price (CLV) is the leading skill indicator, measurable per-bet long before P&L reaches significance | A FROZEN, versioned naive market-implied baseline (vol-scaled drift from prior close). Honest weakening on record: this is not a sharp closing line | YES with engineering — daily prices exist; baseline must be committed, versioned, frozen | Per-prediction "edge vs frozen naive baseline" column; aggregate published as the market-relative skill metric (§6.4) | PH, AT | If always-neutral beats the frozen baseline on the same window, the baseline is mis-specified: re-specify PUBLICLY, bump its version, restate history under both versions | `ENABLE_MARKET_RELATIVE_SKILL` |
| **11. Mechanism-class attribution** | AQR: returns decompose into mechanism classes; a real mechanism must replicate out-of-sample (across sectors/event types), else it's fitted noise | Each prediction tagged with mechanism class (supply shock, rate sensitivity, FX exposure…) at creation | YES — `event_classification` JSON exists in `reasoning_predictions`; needs a fixed taxonomy | Fixed small taxonomy (≤8 classes) in the constitution; per-class Brier/BSS attribution page; replication rule: a class is "trusted" only if BSS>0 in ≥2 sectors | AU, AT | If after 2 quarters no class reaches 20 resolved samples, the taxonomy is too fine — collapse it; self-tagging audited by spot-check (tags are LLM output: U=1) | `ENABLE_MECHANISM_TAGS` |
| **16. Loss-scenario gate** | Renaissance: never trade a signal you can't explain losing money on; explanation bought allocation, statistics alone bought only a small one | Causal-chain audit step exists to extend; loss scenarios must be CHECKABLE against resolved misses, not prose | PARTIAL — audit exists (`trust/layers/evidence.py` wraps chain validation); checkability needs the resolution comparison | Required `loss_scenario` field per prediction (one sentence, machine-comparable driver tag); on each miss, resolver records whether the documented scenario materialized | AT, AU | If in resolved misses the documented scenario matches the actual driver <20% of the time after 50 misses, scenarios are boilerplate — delete the field | `ENABLE_LOSS_SCENARIO_GATE` |

### Tier 2 — precondition met after small forward-only schema work

| Mechanism | Why it works there | Precondition | MO meets it? | Concrete small adaptation | Pillar | Kill criterion | Flag |
|---|---|---|---|---|---|---|---|
| **8. Conformal sets + ACI** | Split conformal gives P(true class ∈ set) ≥ 1−α with a finite-sample, distribution-free guarantee; ACI (Gibbs–Candès) restores target coverage under regime shift with a one-line online α update | Resolved rows with per-class probability vectors; sequential resolution feed | MOSTLY — probs reconstructable via `forecast_vector()` from stored direction+confidence; persist them explicitly going forward | Publish a conformal SET over {bullish, bearish, neutral} at α=0.10 beside each confidence; ACI updates α per resolution; coverage plot on the honesty dashboard ("≥90% is a theorem") | PH, AU | If realized coverage drifts >5 points from target for 2 consecutive months, the implementation is broken (ACI provably prevents this) — unpublish sets pending fix | `ENABLE_CONFORMAL_SETS` |
| **10. Quantile scoring (WIS now → CRPS later)** | Proper scores over distributions, not classes; WIS decomposes into sharpness + over/under-prediction (you see WHY a model is bad) and approximates CRPS | Persisted forecast quantiles + realized outcomes | PARTIAL — 5/16/84/95 percentiles already in `full_json`; WIS-2 computable on EXISTING rows; CRPS needs ~9+ quantiles persisted forward | Step 1: WIS on existing quantiles, published with decomposition. Step 2: widen the persisted quantile set (forward-only, inside `full_json`), graduate to CRPS + rank histogram | PH, AU | If MC rank histogram is extreme-U (intervals badly overconfident) and recalibration doesn't beat climatology CRPS within 2 cycles, STOP publishing MC intervals — known-bad intervals violate the honesty pillar | `ENABLE_QUANTILE_SCORING` |
| **15. Regime-shift alarm (adversarial validation)** | Kaggle/Uber: a classifier distinguishing calibration-window rows from live rows detects distribution shift; AUC≈0.5 = same regime, importances name what drifted | Persisted per-prediction feature vectors for both windows, consistent schema | PARTIAL — snapshot features exist; needs a versioned feature schema (shared prerequisite with meta-labeling) | Weekly job: classifier on calibration-vs-live rows; AUC>0.6 → "calibration stale" banner on the dashboard + top drifted features listed | AT, PH | If the alarm fires in >50% of windows (crying wolf) or fails to fire across a KNOWN regime break replayed from history, delete it | `ENABLE_REGIME_SHIFT_ALARM` |

### Tier 3 — gated on ledger size N (state the number; wait for it)

| Mechanism | Why it works there | Precondition | MO meets it? | Concrete small adaptation | Pillar | Kill criterion | Flag |
|---|---|---|---|---|---|---|---|
| **13. Meta-labeling** | A second model predicting "is the primary right?" trades recall for precision by vetoing likely false positives; needs exactly a resolved prediction ledger with prediction-time context | N ≈ 150–300 resolved (pooled, logistic, 2–4 features); purged/embargoed CV from day one (label intervals overlap); model artifact pinned + hashed for replay | NOT YET — N unknown locally, likely below; feature schema shared with #15 | When N reached: pooled logistic on {vote margin, MC stability, trend regime, event class}; output filters/sizes but NEVER raises confidence above the existing caps; paired-logged against the hand confidence layer | AT, AU | Pre-registered: if purged-CV AUC ≤ 0.55 OR meta-probabilities calibrate worse than the existing confidence layer on holdout, do not deploy; re-attempt only after +150 further resolutions | `ENABLE_META_LABELING` |
| **14. DSR + PBO reporting** | Best-of-N results are inflated by selection; DSR raises the significance hurdle with trial count, PBO measures whether IS winners persist OOS | A COMPLETE trials register (#4) + strategy-level return series over meaningful T; PBO needs all N candidates' series retained | NOT YET — register must exist first; T too short | When paper-trading return series exist: publish DSR beside any Sharpe-like number and PBO beside any backtest, both on the falsification page (§4 surpass axis 3) | PH, AU | If the register is found incomplete (see #4), DSR/PBO numbers are UNPUBLISHED — a DSR computed from an undercounted N is disinformation with a formula on it | `ENABLE_DSR_PBO_REPORT` |
| **17. Sector bias correction** | ECMWF reforecasts: systematic per-regime/per-season bias measured on history and subtracted from live forecasts | Enough resolved predictions per sector/regime bin (≥30/bin) to estimate bias beyond noise | NOT YET — bins will be sparse for quarters | When bins fill: per-sector mean bias from resolved ledger subtracted from forecast probabilities, paired-logged against uncorrected | AT | If corrected BSS ≤ uncorrected BSS on the following out-of-sample quarter, delete the correction (it memorized noise) | `ENABLE_SECTOR_BIAS_CORRECTION` |

### Special rows

| Mechanism | Status |
|---|---|
| **12. TSFM benchmark agent** (Tier 2½) | Precondition met (daily closes + CPU) BUT it is the table's only new heavy dependency — the Architect Directive's no-unjustified-dependencies rule makes this an RFC-level decision, not a default adoption. Adaptation: ONE pinned small checkpoint (Chronos-Bolt or Lag-Llama), seeded/deterministic for replay, mapped to 3-class via P(return>+θ)/P(<−θ), scored in the same ledger. Pillars: AT, PH. Kill: if deterministic pinned inference cannot be achieved (replay violation) or per-day CPU cost exceeds budget, reject regardless of skill. Flag: `ENABLE_TSFM_BENCHMARK` |
| **Kelly sizing (Thorp)** | ALREADY ADOPTED — `services/position_sizer.py`: quarter-Kelly, shrinkage prior toward no-edge, "no measured edge → no position" at <20 resolutions. Retroactive precondition check PASSES (ledger-measured win rate, not agent confidence). Definition-of-done entry: master = Thorp/Kelly 1956; evidence = position sizes respond to track record; residual gap = paper-P&L ledger evidence that quarter-Kelly outperforms flat sizing is NOT yet published — add to honesty dashboard backlog |

---

## 3. Rejection list (published deliverable, per §1 of the directive)

| # | Technique (source) | Reason for rejection | Revisit condition |
|---|---|---|---|
| R1 | **Extremizing the aggregate** (GJP; Satopää) | Precondition FAILS: requires forecaster independence/information diversity; the optimal factor →1 as information overlap rises. MO's agents share one base LLM — extremizing amplifies shared bias | After H2 delivers measurably decorrelated inputs (different base models / disjoint feeds), re-run the precondition check with #7's correlation matrix as evidence |
| R2 | **Superforecaster selection & inter-agent teaming** (GJP) | Agents are not independent samples to select among; small-N per-archetype selection is noise-mining; LLM "discussion" risks sycophancy cascades, not information exchange | Genuine independence (R1's condition) AND per-archetype N ≥ 100 |
| R3 | **Real-money market mechanisms** (Metaculus/markets) | Identity + regulatory: paper-only is a pillar; Australian financial-services law risk; M6 showed accuracy≠returns anyway | Not revisited by this directive; Stage 7 gate governs anything real-money and is itself hard-blocked |
| R4 | **AFML data-structures half** (tick/dollar bars, microstructure, fractional differentiation, HRP) | Requires tick data and portfolio capital MO lacks; fails transfer rule #2 outright | MO acquires intraday data feeds (no current plan) |
| R5 | **End-to-end learned market model** (GraphCast analogy) | ERA5 is ~10⁶× denser than any prediction ledger; markets lack stationary physics; sample size is decades away. The flywheel (dataset+scorecard) transfers, the model does not | Never at MO's scale; the flywheel is adopted instead (#1, #5, #10) |
| R6 | **The 101 alphas as production signals** (WorldQuant) | Published = expired/stylized; adopting them imports decayed signals and a false sense of edge. The SHAPE (short, testable, decaying formulas) informs a possible factor-testbed benchmark, deferred to Phase C's strongest-opponent question | If a factor testbed is chosen as a benchmark in Phase C, formulas are written fresh and register-logged (#4), never copied |
| R7 | **Fine-tuning a TSFM on ASX data** (Chronos et al.) | Measured payoff in the financial-returns literature is negligible; real compute cost; overfitting risk at MO's N | Published evidence of fine-tuning gains on daily equities at small N |
| R8 | **Trained/weighted ensembles** (Forecast Hub) | Needs long per-model track records; the Hub's own trained ensembles barely beat the equal-weight median. Equal-weight median first (#5) | Per-archetype N ≥ 100 AND the median demonstrably calibrated |
| R9 | **Weighted conformal via likelihood ratios** (Tibshirani et al.) | Likelihood-ratio estimation is fragile at MO's N; ACI achieves the same validity goal with a one-line update and no density estimation | If ledger N grows enough that density-ratio estimation stabilizes (not expected soon) |
| R10 | **Secrecy as edge** (Renaissance, syndicates) | Anti-identity: MO's moat is process and proof, not concealment. AQR is the existence proof that publishing builds the franchise when the edge is process | Never — identity lock |

---

## 4. Standing benchmark candidates (§6) — Phase B stance for the RFC to finalize

| §6 item | Covered by row | Phase B stance |
|---|---|---|
| 1. Naive/seasonal-naive/exp-smoothing agents | #1 | ACCEPT — rank 1 |
| 2. Zero-shot TSFM agent | #12 | ACCEPT CONDITIONALLY — dependency + replay determinism must clear RFC review |
| 3. Climatology-prior agent | #3 | ACCEPT — rank 3; per-ticker, never pooled, enforced by kill criterion |
| 4. Market-relative skill score | #9 | ACCEPT — with the baseline-validation caveat written into the metric's published definition |
| 5. CRPS on MC distributions | #10 | ACCEPT STAGED — WIS on existing quantiles first, CRPS after forward-only quantile widening |
| 6. Spread–error calibration | #2 | ACCEPT — rank 2; cheapest genuinely-new information in the table |
| 7. DSR + PBO on published backtests | #14 (+#4) | ACCEPT STAGED — the register NOW, the formulas when T and trials exist; publishing formulas without the register is rejected as false assurance |
| 8. Conformal wrapper on confidences | #8 | ACCEPT — strongest brand-fit mechanism; ACI variant specifically |

Neither blanket acceptance nor blanket rejection: all eight are accepted in
some form, but three (2, 5, 7) only in staged/conditional form, and each
carries its own kill criterion above. The reasoning is per-row, as §6 demands.

**Strongest-opponent preview** (Phase C must answer formally): the single
benchmark most threatening to the swarm's usefulness claim is the
**climatology-prior agent (#3)** — per-ticker base rates are exactly what a
directional swarm must beat for its geopolitical reasoning to have any value,
M6 says most systems fail this bar, and MO's scoring module already computes
it, so there is no engineering excuse. The market-relative baseline (#9) is
the close second; it is the harder PR loss but the weaker statistical
opponent until its own validation caveat is resolved.

---

## 5. Phase C candidates (top 3 by rubric, for the Adaptation RFC)

1. **#1 + #3 Baseline & climatology benchmark agents** (9/10 twins — one RFC
   item: the benchmark-opponents package, incl. the strongest-opponent answer)
2. **#2 Spread–error calibration** (9/10 — new information about the swarm
   itself, computable from the existing ledger, pure verify-script + page)
3. **#4 Trials register** (8/10 — the only mechanism that gets STRICTLY more
   expensive to adopt the longer we wait; every experiment run unregistered
   is unrecoverable N)

Ranks 5–7 (leaderboard, triple-barrier, correlation audit) are next in line
and all Tier-1 cheap; #8 conformal is the highest-leverage Tier-2 item once
per-class probabilities are persisted forward.

---

## 6. Acceptance amendment (2026-07-03) — evidence, corrections, re-ranking

Phase B was ACCEPTED WITH CORRECTIONS. The ordered analysis lane executed
same-day (`docs/analyses/2026-07-03-*.md`); its evidence amends the table:

**6.1 Trials register — removed from ranking, ADOPTED.** Implemented per the
hygiene ruling: hash-chained `docs/trials/register.jsonl` (12 backfilled
entries citing introducing commits — incl. the position_sizer K=20 shrinkage
constant and all Phase 0–B threshold choices — plus live corrections),
appender `backend/scripts/append_trial.py`, verifier
`scripts/verify/verify_trials_register.py`, tests green. Epoch note: pre-2026-07-03
trials are undercounted; all multiplicity corrections over pre-epoch work use
lower-bound N.

**6.2 Spread–error (row 2) — DOWNGRADED on evidence.** Executed analysis
returned a null (Spearman −0.03; terciles indistinguishable; and dispersion
varies only 0.69–0.99 — the swarm is always split, so the diagnostic has
little variation to work with). Precondition now judged PARTIALLY FAILED.
The pipeline page loses its Phase C slot; spread-conditioned confidence
logic is banned while the null stands; re-run at ≥50 independent clusters.

**6.3 Rows 5 and 7 (leaderboard, correlation audit) — preconditions FLIP TO
NOT MET.** The availability audit found `simulations.agent_votes` is an
empty list in 147/147 rows; no persisted surface has per-agent identity.
Per-archetype history is unrecoverable retroactively — every unfixed week
loses comparison-N forever. This creates the new row 0:

**6.4 NEW ROW 0 — Ledger schema completion (master: GraphCast lesson —
"the verified dataset is the crown jewel").** Persist per prediction:
per-agent votes `{agent_id, archetype, vote}`, the per-class probability
vector, a wider MC quantile set, and a versioned feature vector. Rubric
2/2/2/1/2 = **9** and it UNBLOCKS rows 5, 7, 8, 13, 15 plus H2/H7.
Rank #1 pipeline adaptation. Kill criterion: shadow-persistence only —
if written fields alter any existing output byte (replay regression), or
per-agent payloads fail to reconcile with aggregate vote counts on >1% of
rows, revert the writer.

**6.5 Meta-labeling (row 13) — gate corrected via primary source (register
seq 13).** Peduzzi et al. 1996: 10–20 events per variable ⇒ 3–5 features
need 30–100 events of the RARER outcome class (~60–200 resolved), not
"150–300 resolved." Snapshot has ~31 rarer-class events but only 19
independent clusters — clusters, not raw N, are the binding constraint. The
"revisit rank if N≥150" clause is NOT triggered; rank unchanged, gate now
correctly derived: ≥30–100 rarer-class events AND ≥50 clusters.

**6.6 Kelly row — evidence attached.** Retroactive recompute
(`2026-07-03-kelly-vs-flat.md`): growth indistinguishable from flat (+0.33%
vs +0.41% over 68 positions); max drawdown 1.42% vs 4.09%. Risk case holds;
growth claims remain banned. Correction from Thorp 2006 §7.3: fractional
Kelly at fraction c keeps growth c(2−c) (half-Kelly ⇒ 75%) and scales the
STANDARD DEVIATION by c — "half the variance" in §2.1 of the dossier should
read "half the standard deviation (quarter of the variance)."

**6.7 Benchmark-opponents split (acceptance ruling).** Two lanes:
(a) **ANALYSIS — retroactive scoring**: freeze and pre-register baseline
definitions in the trials register FIRST, then score them as-of each
historical prediction date (no look-ahead: climatology uses only
prior-resolved rows; persistence uses only prior closes) across the existing
resolved ledger. Because baselines are reconstructable as-of-date, NO
comparison-N is lost while Stage 2c holds the pipeline queue.
(b) **PIPELINE — standing agents**, flag-gated (`ENABLE_BASELINE_AGENTS`,
`ENABLE_CLIMATOLOGY_AGENT`), emitting rows at prediction time once approved.

**6.8 TSFM ruling (row 12) — recorded verbatim.** Isolated OPTIONAL service
only; never a core-pipeline import. Pin model name, version, weights hash,
and seed; persist outputs to the ledger at prediction time. Verify scripts
attest provenance (hashes) and recompute the quantile→class mapping from the
persisted quantiles. REPLAY READS RECORDED OUTPUTS, NEVER RE-RUNS THE MODEL.
Conditional-accept stance in §4 upgraded to accept-under-this-ruling;
implementation priority unchanged (below the top 3).

**6.9 Re-ranked Phase C top-3 (PIPELINE lane):**
1. **Row 0 — ledger schema completion** (9/10; unblocks five rows + H2;
   unrecoverable-loss argument makes delay the most expensive option)
2. **Rows 1+3 — benchmark-opponents standing agents** (9/10 twins; the
   strongest-opponent answer stands: climatology-prior first — snapshot
   preview raises the stakes: swarm Brier ≈ 0.65 barely beats uniform 0.667)
3. **Row 8 — conformal sets + ACI** (7/10; probabilities reconstructable
   from stored direction+confidence today, cleaner after row 0)

**STOP — Phase B (as amended) ends here. No implementation code. Phase C RFC:
`docs/rfc-masters-adaptations.md`.**
