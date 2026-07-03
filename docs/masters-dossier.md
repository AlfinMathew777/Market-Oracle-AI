# Masters Dossier — Prediction Masters Directive, Phase A

Status: DRAFT — Phase A complete, awaiting approval. No code changed.
Method: 6 parallel web-research agents, one per §2 category of the directive;
sources cited per page. Mechanism candidates are FLAGGED here, not adopted —
extraction-table rigor (precondition check, rubric score, kill criterion,
flag name) is Phase B.

Honest frame (binding): methods, aggregation math, evaluation discipline,
uncertainty quantification, anti-overfitting machinery, and process culture
transfer. Proprietary data, capital, execution speed, and decades of resolved
history do not. Any candidate whose value depends on the latter is rejected
on sight. "Better than them" means: match on method quality; exceed only on
transparency, published adversarial robustness, and public anti-self-deception
tooling. Raw-accuracy superiority claims are banned — only the ledger speaks.

---

## 0. Ground truth — preconditions MO already meets (verified in code)

Checked against the current repo so precondition flags below are facts, not
guesses:

| Capability | Where | Status |
|---|---|---|
| Hash-chained, tamper-evident ledger | `backend/trust/ledger.py`, `verify_chain()` | LIVE |
| 3-class Brier + log loss | `backend/trust/scoring.py` | LIVE |
| BSS vs uniform AND climatology baselines | `trust/scoring.py` (`brier_skill_score`, `climatology_probs`) | LIVE |
| Reliability bins, ECE, Murphy decomposition | `trust/scoring.py` | LIVE |
| Per-signal agent vote counts logged | signal-quality rules (required logging) | LIVE |
| Pre-registered thresholds as code | `trust/constitution.py` (versioned articles) | LIVE |
| Five-layer veto gateway, fail-closed | `trust/gateway.py` + `trust/layers/` | LIVE |
| Wilson-interval track record | `trust/track_record.py` | LIVE |
| Monte Carlo outcome DISTRIBUTIONS persisted | quantiles (5/16/84/95 pct) + stability inside `simulations.full_json`; raw samples NOT persisted | PARTIAL (verified Phase B) |
| Per-prediction feature vectors persisted | `prediction_log`: market snapshot, vote counts, trend_label; `reasoning_predictions`: JSON context | PARTIAL (verified Phase B) |
| Fractional-Kelly position sizing | `services/position_sizer.py` — quarter-Kelly, shrunk win rate, no-edge-until-20-resolutions prior | LIVE (found Phase B) |

Two recurring precondition gaps to carry into Phase B: (1) full MC
distributions and prediction-time feature vectors may not be persisted —
several candidates (CRPS, adversarial validation, meta-labeling) need them;
(2) resolved-ledger size N is small — every learned component must state its
minimum N and wait for it.

---

# §2.1 Quantitative finance

## Renaissance Technologies / Medallion Fund

**Sources:** Gregory Zuckerman, *The Man Who Solved the Market* (Portfolio/Penguin, 2019); [CFA Institute review](https://blogs.cfainstitute.org/investor/2020/05/01/book-review-the-man-who-solved-the-market/); [practitioner notes](https://novelinvestor.com/notes/the-man-who-solved-the-market-by-gregory-zuckerman/).

**Mechanism.** (1) Tiny edges × enormous N — Mercer: right "50.75 percent of
the time… but 100 percent right 50.75 percent of the time." Profit is the law
of large numbers over thousands of short-horizon, largely independent bets.
(2) Every signal is treated as perishable; monitored for decay, retired when
crowded. (3) Data hygiene as core research, not plumbing — Straus's obsessive
price cleaning is portrayed as a foundational edge; the errors you don't find
become your "alpha." (4) Unexplained signals trade only at limited size until
someone can articulate why the anomaly exists — including how it loses money.
(5) One unified model/book with centralized risk, not siloed strategies.

**Why it works there:** decades of cleaned proprietary data, leverage,
execution infrastructure, secrecy.

**Mechanism candidates for MO:**
- Many small bets judged in aggregate — optimize for prediction *count* and
  fast resolution, not per-call confidence. Precondition: ledger statistics —
  met.
- Assume signal decay: timestamp and periodically re-test agent-consensus
  patterns. Precondition: dated, versioned ledger — met.
- Data hygiene as first-class discipline: news timestamps, look-ahead bias in
  event data, ASX corporate actions. Precondition: rigor only — met.
  Look-ahead leakage is MO's biggest silent killer.
- "Explain how it loses money" gate — extend the existing causal-chain audit
  to require a documented losing scenario per prediction. Precondition: audit
  step exists — met.

**Not extractable / rejected:** petabyte proprietary data, decades of history,
leverage/capital, sub-second execution, 90 PhDs, and secrecy — MO's identity
is the opposite of secrecy.

## Ed Thorp

**Sources:** Thorp, *A Man for All Markets* (2017) ([CFA review](https://rpc.cfainstitute.org/research/financial-analysts-journal/2017/a-man-for-all-markets)); Kelly, "A New Interpretation of Information Rate," *Bell System Technical Journal* 35 (1956); Thorp, "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market" (2006); MacLean, Thorp & Ziemba, *The Kelly Capital Growth Investment Criterion* (2011).

**Mechanism.** (1) Kelly sizing: optimal bankroll fraction f\* = edge/odds
(binary: f\* = (bp − q)/b; continuous: f ≈ μ/σ²). Stake proportional to
MEASURED edge; zero edge → zero stake. (2) Fractional Kelly for estimation
error: edges are estimates, and overestimating means unknowingly betting past
full Kelly where growth turns negative; fractional Kelly at fraction c keeps
c(2−c) of the growth rate and scales the standard deviation by c — half-Kelly
gives ~75% of growth at half the std-dev, a quarter of the variance (Thorp
2006 §7.3; corrected 2026-07-03 after primary-source verification).
Survival precedes edge. (3) Verify empirically at small
stakes before scaling — low-minimum tables first, paper first. (4) An
unmeasured edge is not neutrality; it is a measured edge of zero.

**Mechanism candidates for MO:**
- Kelly as the confidence-to-stake converter in paper trading — position
  weight a function of *ledger-measured* edge, not agent-vote confidence.
  Precondition: calibration data from the ledger — met once N suffices.
- Fractional Kelly as institutional humility — formalize the 85% cap as
  quarter-Kelly on estimated edge. Precondition: none — met.
- "No measured edge → no bet": abstain/NEUTRAL as a first-class, scored
  outcome. Precondition: already policy — met (verify it is scored, not just
  excluded).
- Small-stakes verification ladder: flags-default-off + paper mode ARE
  Thorp's low-minimum tables. Already MO practice.

**Not extractable / rejected:** known-probability games (markets never grant
this), convertible-hedging capital, personal execution. The math transfers;
casino-grade certainty does not.

## WorldQuant

**Sources:** Kakushadze, "101 Formulaic Alphas," [arXiv:1601.00991](https://arxiv.org/abs/1601.00991), *Wilmott* (2016) — appendix lists all 101 formulas.

**Mechanism.** (1) Alphas are short formulas, not theories: one-to-few-line
expressions over price/volume primitives with a small operator vocabulary —
cross-sectional `rank()`, `ts_rank`, `delay`, `delta`, `correlation`,
`decay_linear`. Ranking is the workhorse: it converts noisy levels into
relative bets and neutralizes market direction. (2) Short horizons — average
holding period 0.6–6.4 days; fast, self-liquidating bets. (3) Diversification
by low correlation — average pairwise alpha correlation 15.9%; power comes
from many weak decorrelated signals. (4) The real asset is the alpha FACTORY:
mass-produced candidate formulas, every one scored by a single shared
evaluation harness (same universe, same costs, same gates); survivors
combined, decayed alphas cycled out.

**Mechanism candidates for MO:**
- Shared evaluation harness: the ledger + pre-registered resolution + Brier
  machinery IS a harness. Treat every agent persona / prompt variant as a
  candidate alpha, scored individually. Precondition: met.
- Mass hypothesis testing: LLM agents generate hypotheses at ~zero marginal
  cost; the bottleneck is resolved outcomes → prefer short-horizon
  predictions to grow N fast. Precondition: met.
- Correlation screening among agents: measure pairwise agreement; 40 agents
  that always agree are one agent. Prune/re-prompt toward decorrelation
  (this is the H2 correlation work, independently rediscovered). Precondition:
  per-agent vote history — met.
- Rank, don't level: predict *relative* ordering of ASX tickers per event —
  more testable than absolute direction. Precondition: multi-ticker output —
  partially met.
- Factor testbed scored by the existing ledger machinery (directive's
  suggestion) — a small library of formulaic signals over ASX dailies as
  benchmark opponents. Precondition: daily OHLCV — met.

**Not extractable / rejected:** intraday execution, shorting infrastructure,
thousands of consultants, survivorship-vetted feeds; the 101 formulas
themselves are stylized/expired — copy the SHAPE, not the formulas.

## AQR

**Sources:** Asness, Moskowitz & Pedersen, "Value and Momentum Everywhere," *JF* 68(3) 2013 ([PDF](https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf)); Asness, Frazzini & Pedersen, "Quality Minus Junk," *RAS* 24 (2019); Alquist, Israel & Moskowitz, ["Fact, Fiction, and the Size Effect"](https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Fact-Fiction-and-the-Size-Effect.pdf) (2018); Asness, Ilmanen & Maloney, "Sin a Little" (JOIM 2017).

**Mechanism.** (1) Factor thinking: returns decompose into a few persistent,
economically motivated cross-sectional characteristics (value, momentum,
quality); a "prediction" is exposure to a mechanism class, not a story about
one stock. (2) Out-of-sample discipline via breadth: the same two signals
tested across eight markets/asset classes; a real mechanism must replicate in
data it was never fitted on. Value and momentum are ~−0.5 correlated, so the
combination dominates either. (3) They publish negative results about their
own industry's products — the size effect is weak ("Fact, Fiction"), factor
timing barely works ("Sin a Little"). Publishing methodology invites
replication and makes surviving claims credible.

**Mechanism candidates for MO:**
- Cross-replication as the out-of-sample test: an event→ticker mechanism must
  replicate across sectors or event types before it is trusted; a mechanism
  that only works on lithium miners is probably fitted noise. Precondition:
  mechanism tagging — cheap.
- Factor framing for agent reasoning: tag each call with its mechanism class
  (supply shock, rate sensitivity, FX exposure), score accuracy per class —
  MO's version of factor attribution. Precondition: none — met.
- Publish negative results as a trust asset: AQR is the existence proof that
  publishing methodology and failures BUILDS the franchise when the edge is
  process, not secrets. Validates MO's identity pillar directly.
- Scheduled skeptical self-audits ("Fact, Fiction, and MO's accuracy") of
  MO's own headline claims. Precondition: resolved N — later.

**Not extractable / rejected:** decades of multi-market data, institutional
patience through 3-year droughts, shorting/derivatives infrastructure; the
premia themselves aren't MO's game — event reactions, not long-run factors.

## Marcos López de Prado — Advances in Financial Machine Learning

*(Flagged in the directive as the highest-leverage single source; this page
runs long deliberately.)*

**Sources:** López de Prado, *Advances in Financial Machine Learning* (Wiley 2018), Ch. 3, 3.6, 7, 10–14; Bailey & López de Prado, "The Deflated Sharpe Ratio," *JPM* 40(5) 2014 ([SSRN 2460551](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)); Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest Overfitting," *J. Comput. Finance* 20(4) 2017 ([SSRN 2326253](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)); López de Prado & Bailey, "The False Strategy Theorem" ([SSRN 3221798](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3221798)); [Hudson & Thames meta-labeling explainer](https://hudsonthames.org/meta-labeling-a-toy-example/).

**Mechanisms.**
1. **Triple-barrier labeling.** Per prediction event: upper barrier at
   p₀·(1 + pt·σₜ), lower at p₀·(1 − sl·σₜ), vertical at t₀+h; σₜ is a rolling
   (EWMA) vol estimate so barrier width adapts per instrument. Label = first
   barrier touched (+1 / −1 / 0-or-sign-at-expiry). Fixed-horizon labels are
   flawed because (a) a constant threshold ignores heteroscedasticity — the
   same +1% is noise for a volatile miner and signal for a utility; (b) they
   ignore the path (an intra-horizon stop-out gets labeled a win); (c) label
   difficulty is non-stationary across regimes. ~50 lines to implement.
2. **Meta-labeling.** Keep the primary model (decides side); train a
   secondary binary classifier on "was the primary's prediction correct?"
   with features describing the conditions of success (primary confidence,
   vote dispersion, regime/vol state, recent hit rate). Use its probability
   to FILTER (skip below threshold) and SIZE. Improves precision/F1 by
   vetoing likely false positives rather than finding new winners. Training
   data required: a history of primary predictions paired with resolved
   outcomes and prediction-time context. **MO's verified ledger is exactly
   this dataset — the single strongest structural match in the entire
   dossier.** It is a principled, learned upgrade of the existing confidence
   layer, and its output naturally respects the 85% cap.
3. **Purged + embargoed k-fold CV.** Horizon-based labels are intervals, not
   points; naive k-fold lets a training label whose interval overlaps a test
   interval leak the test outcome, inflating CV scores. Purge: drop training
   rows with overlapping label intervals; embargo: also drop a buffer (~1%)
   immediately after the test window against serial correlation. Mechanically:
   store (t₀, t₁) per label; drop where [t₀ᵢ,t₁ᵢ] ∩ [test window + embargo]
   ≠ ∅. MO's ledger already stores prediction time and resolution time — the
   interval exists.
4. **Deflated Sharpe Ratio.** The best Sharpe among N tried variants is
   inflated by selection. DSR = PSR against a raised hurdle SR\* that grows
   with the number and variance of trials (≈ √V[SR]·[(1−γₑ)·Z⁻¹(1−1/N) +
   γₑ·Z⁻¹(1−1/(N·e))]), with a penalty for skew/kurtosis and short track
   length. After ~100 trials, pure noise yields an expected best backtest
   Sharpe ≈ 2.5. Practical requirement: COUNT AND LOG EVERY TRIAL.
5. **Probability of Backtest Overfitting (CSCV).** Matrix of period returns
   for all N candidate configurations; over all symmetric in-/out-of-sample
   block splits, find the IS winner's OOS rank; PBO = fraction of splits
   where the IS winner is below OOS median. PBO ≈ 0.5 → selection is a coin
   flip. Requires retaining ALL candidates' return series, not the winner's.
6. **The core sin + False Strategy Theorem.** Expected max Sharpe over N
   zero-skill trials grows ~√(2·ln N) — unbounded — so without knowing N, no
   backtest result is evidence of skill. Never adjust a strategy in response
   to its backtest (each adjustment = a new trial); a backtest is a sanity
   check on an independently formed hypothesis, not a discovery tool.

**Mechanism candidates for MO (with honest N-arithmetic):**
- **Meta-labeling on the ledger — highest-value transplant.** Minimum N by
  the 10–20 events-per-variable rule: ~150–300 resolved predictions pooled
  across tickers for a 3–5-feature logistic meta-model; ~1,000+ for trees or
  per-sector models; per-ticker models are years away. TODAY: borderline —
  pooled, logistic, 2–4 features only. Design the ledger schema NOW to
  persist prediction-time features.
- **Triple-barrier resolution criteria** — volatility-scaled barriers,
  pre-registered per prediction. Needs only daily OHLC + per-ticker EWMA vol.
  TODAY: yes. Fixes a real current flaw: a +0.8% move counts as a "hit" for a
  low-vol stock but is noise elsewhere; makes Brier comparable across tickers.
- **Trials register** (DSR discipline) — log every configuration/prompt/
  threshold variant ever evaluated, beside the ledger. Near-zero cost, adopt
  immediately; compute an actual DSR later when strategy-level paper returns
  exist. The same logic deflates the best-of-N Brier Skill Score.
- **PBO/CSCV** — LATER; needs a T×N matrix MO doesn't have. Interim honest
  substitute: pre-registration + publish-negative-results already blocks the
  selection channel PBO measures.
- **Purged/embargoed CV** — CONDITIONAL: mandatory from day one of training
  ANY learned component (incl. the meta-model) on overlapping-horizon ledger
  labels.

**Not extractable / caution:** the data-structures half of AFML (dollar/tick
bars, microstructure, fractional differentiation, HRP) presumes tick data and
capital allocation MO doesn't have — don't cargo-cult. A meta-model at N≈10²
can itself overfit: validate it with the same purged-CV + trial-counting
discipline it enables, or overfitting just moves up one level — logistic
regression first, never gradient boosting first. DSR/PBO cannot rescue a
process that didn't log discarded trials; the register cannot be retrofitted.
None of his published evidence covers ~10²-sample LLM event-reaction
predictions — treat every transplant as a hypothesis for MO's own ledger to
confirm.

---

# §2.2 Forecasting science

## Philip Tetlock / Good Judgment Project

**Sources:** Tetlock & Gardner, *Superforecasting* (2015); [Mellers et al. 2014, *Psychological Science*](https://journals.sagepub.com/doi/10.1177/0956797614524255); [Satopää et al., logit aggregation/extremizing](https://www2.math.upenn.edu/~pemantle/papers/aggregation.pdf); [Atanasov et al. 2016, *Management Science*](https://pubsonline.informs.org/doi/10.1287/mnsc.2015.2374).

**Mechanism.** GJP won IARPA's ACE tournament with stackable, individually
measured interventions: (1) outside view FIRST — anchor on a reference-class
base rate before case-specific adjustment; (2) Fermi decomposition into
estimable sub-questions; (3) granular probabilities — rounding
superforecasters to the nearest 5–10% measurably worsens Brier; (4) frequent
micro-updates, not rare jumps; (5) 1-hour calibration training, teaming, and
tracking top 2% each independently improved accuracy; (6) aggregation with
EXTREMIZING (optimal factor ~1.2–3.9) — because averaging INDEPENDENT,
partially informed forecasters is systematically underconfident.

**Why it works there:** hundreds of humans with genuinely diverse information
sources; thousands of resolvable questions; incentives tied to accuracy.

**Mechanism candidates for MO:**
- **Climatology-prior / outside-view-first agent** — force a base-rate
  forecast ("ASX materials reaction to comparable events") that every
  archetype must beat to matter. Precondition: a base-rate library from
  historical events — buildable; `climatology_probs()` already exists in
  scoring.
- Fermi decomposition: split "bullish BHP?" into pre-registered sub-claims
  (shipping disruption? price pass-through?), scored separately. Precondition:
  sub-question resolution in the ledger — supported.
- Granular probabilities under the 85% cap — cheap; met.
- **EXTREMIZING — DO NOT ADOPT (formal rejection candidate).** Precondition
  is forecaster independence/information diversity; the optimal extremizing
  factor shrinks toward 1 (no adjustment) as information overlap rises. MO's
  agents share one base LLM — extremizing would amplify a shared bias, not
  sharpen a signal. Revisit only after H2 delivers genuinely independent
  inputs (different models, disjoint feeds).

**Not extractable / rejected:** superforecaster selection (top-2% tracking) —
MO's agents aren't independent samples to select among; inter-agent
"teaming"/discussion risks LLM sycophancy cascades, not information exchange.

## M-competitions (Makridakis: M4, M5, M6)

**Sources:** [Makridakis, Spiliotis & Assimakopoulos 2020, "The M4 Competition," *IJF*](https://www.sciencedirect.com/science/article/pii/S0169207019301128); [M5 Accuracy, *IJF* 2022](https://www.sciencedirect.com/science/article/pii/S0169207021001874); [Makridakis et al., "The M6 forecasting competition," *IJF* 2024 / arXiv:2310.13357](https://arxiv.org/abs/2310.13357).

**Mechanism.** Open competitions where every entrant is scored on held-out
data against PERMANENT simple baselines (Naïve, seasonal Naïve, Naïve2,
exponential smoothing, Theta, "Comb" = average of three ES variants); the
headline number is % improvement over Comb. Empirical record: M4 (100k
series) — 12 of the 17 best methods were COMBINATIONS; all six pure-ML
entries lost to Comb; winner (Smyl) was a hybrid ES+RNN, ~9.4% over Comb.
M6 (100 assets, live 12 months) — only 23% of 163 teams beat the naive
uniform-probability forecast; only 31% beat the equal-weight portfolio; and
correlation between forecast accuracy and investment returns was **r ≈ 0.04**
(r ≈ 0.12 even in the top 5%). Accuracy and profit are essentially
uncorrelated.

**Mechanism candidates for MO:**
- **Baselines permanently inside the benchmark set** — naive persistence,
  "always neutral," uniform, seasonal-naive, exponential smoothing — scored
  on the SAME pre-registered questions, never removed. Precondition: pure
  engineering — met. (Directive §6 items 1 and 3.)
- Report skill as % improvement over the naive baseline, not raw accuracy —
  including when negative. This is BSS discipline generalized; MO already
  computes BSS vs climatology.
- Combination beats sophistication: a plain median across agents is the
  M4-endorsed aggregator; resist clever weighting until the ledger justifies
  it. Precondition for comparisons: resolved N — not yet met; default to
  median meanwhile.
- M6's accuracy≠returns finding validates paper-trading-only and BANS ever
  advertising directional accuracy as tradable edge. Track hypothetical P&L
  vs equal-weight as a separate ledger column so the gap stays visible.

**Not extractable / rejected:** hybrid stat+ML training à la M4 winners
(needs long per-series histories; MO predicts discrete event reactions);
prize-driven participant diversity.

## Metaculus and prediction markets

**Sources:** [Metaculus track record](https://www.metaculus.com/questions/track-record/) (public calibration curves); [Metaculus FAQ — Community Prediction, resolution rules](https://www.metaculus.com/faq/); [Atanasov et al. 2016, markets vs polls, *Management Science*](https://pubsonline.informs.org/doi/10.1287/mnsc.2015.2374).

**Mechanism.** (1) Question operationalization discipline: resolution
criteria, resolution date, and edge-case handling written BEFORE forecasting
opens; ambiguous questions resolve "ambiguous" rather than being
reinterpreted; the resolver is independent of forecasters. (2) Community
Prediction = recency-weighted MEDIAN of each user's latest forecast —
outliers and stale forecasts damped. (3) Public log-score leaderboards and a
published calibration track record over thousands of questions. Atanasov:
statistically aggregated polls (decay + performance weighting +
recalibration) beat real-money markets — aggregation design, not market
structure, does the work.

**Mechanism candidates for MO:**
- Pre-registered resolution + independent resolver — already an MO pillar;
  copy the specifics: numeric thresholds, NAMED resolution data source
  (e.g., ASX close from a stated feed), explicit ambiguous/annulled outcome.
  Precondition: resolver logic as committed code, never edited after — the
  directive already demands verifying this is enforced in code, not
  convention.
- Median aggregation (recency-weighted only if agents update mid-question;
  MO votes once per event → plain median). Precondition: met.
- Public per-archetype calibration curves + Brier/log-score leaderboard —
  serves auditability directly. Small-n curves labeled provisional.
- Peer scoring vs the swarm aggregate to detect which personas add
  information vs echo — interpret gaps cautiously; persona diversity is
  prompt-deep, not information-deep.

**Not extractable / rejected:** real-money mechanisms (Australian regulatory
risk; MO is paper-only); crowd-scale independence — MO must never cite
Metaculus-style aggregation as evidence its correlated swarm is calibrated;
only MO's own resolved ledger can show that.

---

# §2.3 Physical-science forecasting

## ECMWF ensemble forecasting

**Sources:** [ECMWF Forecast User Guide §5 (ENS)](https://confluence.ecmwf.int/display/FUG/Section+5+Forecast+Ensemble+(ENS)+-+Rationale+and+Construction); [IFS Cy49r1 Part V](https://www.ecmwf.int/sites/default/files/elibrary/112024/81627-ifs-documentation-cy49r1-part-v-ensemble-prediction-system.pdf); Leutbecher & Palmer 2008, ["Ensemble forecasting," *J. Comput. Phys.*](https://dl.acm.org/doi/10.1016/j.jcp.2007.02.014); Hersbach 2000, [CRPS decomposition, *Wea. Forecasting*](https://journals.ametsoc.org/view/journals/wefo/15/5/1520-0434_2000_015_0559_dotcrp_2_0_co_2.xml); Fortin et al. 2014, ["Why Should Ensemble Spread Match the RMSE…," *J. Hydrometeor.*](https://journals.ametsoc.org/view/journals/hydr/15/4/jhm-d-14-0008_1.xml).

**Mechanism.** 51 forecasts: control + 50 members with perturbed initial
conditions (singular vectors + ensemble data assimilation) and stochastic
physics (SPPT→SPP), sampling model error as well as initial-condition error.
The DISTRIBUTION is the forecast, and the distribution itself is verified:
- **Spread–error calibration:** in a reliable ensemble, ensemble variance
  equals expected squared error of the ensemble mean; RMSE of the mean should
  match √(mean ensemble variance) (Fortin 2014 — sqrt-of-mean-variance, not
  mean of std-devs). Diagnostics: spread-vs-RMSE by lead time; rank
  (Talagrand) histograms — U-shape = overconfident, dome = underconfident.
- **CRPS** = ∫[F(x) − H(x−obs)]² dx: squared distance between forecast CDF
  and the outcome step function. Strictly proper, scores the whole
  distribution, reduces exactly to MAE for a point forecast. Skill: CRPSS =
  1 − CRPS/CRPS_climatology; Hersbach decomposes into reliability +
  resolution.
- **Reforecasts:** the same model rerun over ~20 past years; lead-time- and
  season-dependent mean error subtracted; model climate defines anomaly
  products.

**Mechanism candidates for MO:**
- **Spread–error calibration on swarm disagreement — testable NOW.** Does
  30–50-agent vote dispersion predict miss probability? Bin the existing
  resolved ledger by spread, compare Brier per bin. Precondition: per-signal
  vote counts in the ledger — MET TODAY. (Directive §6 item 6.)
- **CRPS on Monte Carlo distributions** vs realized returns, beside 3-class
  Brier. Precondition: persisted MC distributions + realized outcomes —
  VERIFY persistence in Phase B. (§6 item 5.)
- Rank histogram: where does the realized return fall within the MC ensemble?
  Flat = honest. Same precondition as CRPS.
- Reforecast-style bias correction per sector/regime from ledger history —
  marginal until the ledger grows.

**Not extractable / rejected:** singular-vector perturbation math (needs a
differentiable dynamical model); treating MO's agents as exchangeable draws
from one model — spread is a signal to CALIBRATE, never to assume reliable.

## DeepMind GraphCast / GenCast (ML weather)

**Sources:** Lam et al. 2023, ["Learning skillful medium-range global weather forecasting," *Science* 382](https://www.science.org/doi/10.1126/science.adi2336); Price et al. 2024, [GenCast, *Nature* 637](https://www.nature.com/articles/s41586-024-08252-9); Rasp et al., [WeatherBench 2](https://arxiv.org/pdf/2308.15560).

**Mechanism — the lesson, not the architecture.** GraphCast (GNN trained on
ERA5 reanalysis 1979–2017) beat the physics-based HRES gold standard on ~90%
of 1,380 targets, scored on the incumbent's OWN per-variable RMSE/ACC
scorecard on held-out years; GenCast then beat the ENS ensemble on 97.2% of
1,320 targets, scored by CRPS. Two ingredients, neither a neural network:
(1) **ERA5 existed** — a uniform, quality-controlled, verified reconstruction
of four decades of truth in one schema; with it, a team with zero forecasting
heritage overtook a 45-year physics program. (2) **Verification on the shared
scorecard** made the claim credible. Honesty caveat the papers acknowledge:
ERA5 is itself produced by ECMWF assimilation — verified datasets encode
their maker's biases.

**Mechanism candidates for MO:**
- **The verified ledger is the crown jewel; every model on top is
  replaceable.** Precondition: ledger uniformity (fixed schema, timestamps,
  resolved outcomes, no retro-edits, no survivorship deletion) — enforce
  structurally (hash chain does this), not culturally.
- **Fixed public scorecard** (Brier + CRPS + spread-error vs frozen
  climatology baseline) so any agent/prompt/model swap is judged on identical
  numbers. Precondition: baseline frozen — cheap, do early.
- Dataset quality beats model sophistication: budget effort into ledger
  completeness and outcome verification BEFORE adding agents or bigger
  models. Directly matches the small-budget constraint.
- Held-out discipline: never tune on periods you report skill for.

**Not extractable / rejected:** the GNN/diffusion architectures (ERA5 is
~10⁶× denser than any prediction ledger; markets lack stationary physics);
training an end-to-end market model from the ledger — sample size is decades
away. The transferable asset is the dataset-and-scorecard flywheel.

---

# §2.4 Epidemic forecasting hubs

## CDC FluSight / COVID-19 Forecast Hub

**Sources:** Cramer et al. 2022, [*PNAS* — evaluation of individual and ensemble COVID-19 mortality forecasts](https://www.pnas.org/doi/10.1073/pnas.2113561119); Bracher, Ray, Gneiting & Reich 2021, [*PLOS Comp Biol* — "Evaluating epidemic forecasts in an interval format" (WIS)](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008618); Reich Lab [covid19-forecast-hub](https://github.com/reichlab/covid19-forecast-hub); [`scoringutils` WIS reference](https://epiforecasts.io/scoringutils/reference/wis.html).

**Mechanism.** 90+ independent groups, tens of millions of predictions, all
forced into ONE standardized submission format: quantile forecasts (23 levels,
0.01–0.99) for pre-registered targets and horizons. The common schema makes
heterogeneous models comparable and a mechanical combination possible. The
weekly multi-model ensemble — for much of the period a simple EQUAL-WEIGHT
MEDIAN across submitted quantiles — was the single most consistently accurate
forecaster over Apr 2020–Oct 2021, beating essentially all component models
across time; individual models were erratic, the median reliably near the top
and better calibrated. Scoring: **Weighted Interval Score** — a proper score,
weighted sum of interval scores across quantile levels plus the median, which
DECOMPOSES into dispersion + overprediction + underprediction penalties (you
see WHY a model scored badly) and approximates CRPS. Every forecast archived
publicly BEFORE resolution; evaluations published regardless of who looked
bad.

**Mechanism candidates for MO:**
- Standardized internal submission format: agents, archetypes, AND baselines
  all emit one canonical forecast object (probabilities or quantiles) on
  fixed targets/horizons. Precondition: schema work — met with engineering.
- **Per-archetype vs ensemble comparison, published** — the Hub's core
  finding predicts MO's median-of-archetypes will beat every individual
  archetype; publish it whichever way it goes. Precondition: per-archetype
  ledger rows — met.
- WIS with decomposition — diagnoses per-archetype bias vs overconfidence.
  Precondition: interval/quantile outputs, not just 3-class calls —
  conditional.
- Pre-resolution public archive + publish failures — matches the ledger
  ethos exactly; the hash chain is MO's stronger version.

**Not extractable / rejected:** trained/weighted ensembles (need long track
records — start equal-weight median); epidemic-specific targets. Only the
format and scoring machinery transfer.

---

# §2.5 Betting syndicates

## Starlizard (Tony Bloom) / Smartodds (Matthew Benham)

**Sources:** [TheJournal.ie 2016 profile of Bloom/Starlizard](https://www.thejournal.ie/tony-bloom-starlizard-2597458-Feb2016/); theesk.org 2026 analyses ([Starlizard](https://theesk.org/2026/04/09/anthony-grant-bloom-analysis-of-starlizard-the-brighton-model-and-the-legal-challenges-to-professional-gambling-integrity/), [Benham](https://theesk.org/2026/04/10/matthew-benham-an-analysis-of-matthew-benhams-statistical-gambling-operations-and-football-governance/)); Pinnacle, ["What is Closing Line Value"](https://www.pinnacle.com/betting-resources/en/educational/what-is-closing-line-value-clv-in-sports-betting); [Buchdahl on CLV](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl).

**Mechanism.** Statistical-arbitrage shops, not bookmakers: researchers log
granular match data → quant models produce fair odds → selectors compare
model odds vs market prices → placers execute through brokers without moving
the line. Edge per bet ~1–3% ROI, harvested via volume and strict
SPECIALIZATION in one deeply understood sport. The key evaluation insight:
the market's CLOSING LINE is the sharpest public probability estimate (it has
absorbed all information and sharp money), so **Closing Line Value —
consistently beating the closing price — is the leading indicator of skill**:
outcomes are noisy and profit takes a huge sample to reach significance, but
CLV is measurable on EVERY bet immediately, before the outcome is known.

**Mechanism candidates for MO:**
- **Market-relative skill score vs a naive market-implied baseline** (§6
  item 4). ASX has no betting line but has prices: use vol-scaled
  drift/momentum-from-prior-close as the "closing line," score every forecast
  as edge vs that baseline, not raw hit-rate. Precondition: baseline defined
  and frozen — met with engineering.
- CLV-style leading indicator: "did the archetype beat the naive baseline?"
  per prediction gives a skill signal long before paper-trading P&L is
  significant. CAVEAT (honest weakening): a self-constructed drift baseline
  is NOT an efficient sharp price — beating it can reflect baseline naivety
  rather than skill. The baseline itself must be validated against realized
  returns before CLV-style scores are trusted.
- Kelly/flat staking discipline — see Thorp page; conviction weighting in
  paper positions only after edges are measured.
- Specialization: concentrate on a small, locked ASX universe rather than
  the whole board. Precondition: deliberate scope limit — an identity fit.

**Not extractable / rejected:** the informational edge itself (proprietary
scouted data, brokered placement) — MO has no counterparty and no line to
steam; staking magnitudes are irrelevant to paper trading.

---

# §2.6 ML competition lore and modern tooling

## Kaggle grandmaster practice

**Sources:** [NVIDIA, "The Kaggle Grandmasters Playbook"](https://developer.nvidia.com/blog/the-kaggle-grandmasters-playbook-7-battle-tested-modeling-techniques-for-tabular-data/); [FastML, "Adversarial validation, part one"](https://fastml.com/adversarial-validation-part-one/); [Antonopoulos, adversarial validation](https://ilias-ant.github.io/blog/adversarial-validation/); [Kaggle Learn, data leakage](https://www.kaggle.com/code/alexisbcook/data-leakage/data); [Pan et al., adversarial validation at Uber, arXiv:2004.03045](https://arxiv.org/pdf/2004.03045).

**Mechanism.** (1) Stacking: base models trained under k-fold CV; their
OUT-OF-FOLD predictions become meta-features for a simple stage-2 model;
diversity (decorrelated errors) is the point. (2) Leakage paranoia: split
before preprocessing; fit transformers on train only; chronological splits
for temporal data — shuffled k-fold "leaks the future." (3) **Adversarial
validation:** concatenate train and test rows, label 0/1, train a classifier
to tell them apart. AUC ≈ 0.5 → same distribution; AUC ≫ 0.5 → shift, and
feature importances name exactly WHAT drifted. Used in first-place fraud
solutions; productionized at Uber for concept-drift detection.

**Mechanism candidates for MO:**
- **Adversarial validation as a regime-shift alarm.** Classifier
  distinguishes calibration-window feature rows from live rows; AUC > ~0.6 →
  calibration is stale, and importances say why (vol regime, sector
  rotation). Precondition: persisted per-prediction feature vectors for both
  periods — VERIFY in Phase B; if features aren't persisted yet, that schema
  change is the prerequisite.
- OOF-style meta-learner over agent votes — converges with López de Prado's
  meta-labeling; same N and time-split preconditions.
- Leakage discipline: confidence calibration must only ever use predictions
  resolved BEFORE the confidence being tuned. Enforce in code.

**Not extractable / rejected:** 500-model experiment farms and multi-level
stacks (budget mismatch); pseudo-labeling (no unlabeled corpus worth
labeling); leaderboard probing (no analogue).

## Conformal prediction

**Sources:** Angelopoulos & Bates 2021, ["A Gentle Introduction to Conformal Prediction," arXiv:2107.07511](https://arxiv.org/abs/2107.07511) (+ [code](https://github.com/aangelopoulos/conformal-prediction)); Vovk, Gammerman & Shafer, *Algorithmic Learning in a Random World* (Springer 2005/2022); Tibshirani et al. 2019, ["Conformal Prediction Under Covariate Shift," arXiv:1904.06019](https://arxiv.org/pdf/1904.06019); Gibbs & Candès 2021, ["Adaptive Conformal Inference Under Distribution Shift," NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html).

**Mechanism.** Split conformal: hold out n resolved examples; compute a
nonconformity score each (e.g., 1 − model probability on the true class);
take the ⌈(n+1)(1−α)⌉/n quantile q̂; at prediction time output the SET of all
labels scoring ≤ q̂. Guarantee: P(true label ∈ set) ≥ 1−α — finite-sample,
distribution-free, for ANY underlying model; the only assumption is
exchangeability. Uncertainty is expressed as set size, not a massaged scalar.
The caveat: time series are not exchangeable. Remedies: weighted conformal
(likelihood-ratio reweighting — fragile at small N) and **Adaptive Conformal
Inference** (Gibbs–Candès): a one-line online update of the effective α after
each observed miss, provably achieving target long-run coverage
IRRESPECTIVE of the data-generating process.

**Mechanism candidates for MO:**
- **Conformal sets over {bullish, bearish, neutral}** at α = 0.10, published
  beside the capped confidence. "Our 90% sets contain the outcome ≥90% of
  the time" becomes a THEOREM, not a track record — the single best
  brand-fit mechanism in the dossier for the provable-honesty pillar (§6
  item 8). Precondition: resolved ledger rows with stored per-class
  probabilities; the guarantee holds at small n, but sets are coarse
  (uninformatively large) until a few hundred rows exist.
- **ACI as the deployment mode** — sets auto-widen when markets shift,
  restoring validity without exchangeability. Precondition: sequential
  resolution feed — met.
- Publish the exchangeability caveat verbatim; pairs coherently with the
  adversarial-validation staleness alarm.

**Not extractable / rejected:** full transductive conformal (refits per
candidate label — infeasible over an LLM swarm); conformalized quantile
regression (MO publishes directional calls, not return intervals — revisit
if that changes); weighted conformal at MO's data scale — prefer ACI.

## Time-series foundation models

**Sources:** Chronos — Ansari et al. 2024, [arXiv:2403.07815](https://arxiv.org/abs/2403.07815) (Amazon); TimesFM — Das et al. 2024 (Google, ICML); Moirai — Woo et al. 2024 (Salesforce); Lag-Llama — Rasul et al., [arXiv:2310.08278](https://arxiv.org/abs/2310.08278); [TSFMs for financial return forecasting, arXiv:2606.27100](https://arxiv.org/abs/2606.27100).

**Mechanism.** Pretrained transformers for zero-shot probabilistic
forecasting: feed raw history, get a forecast distribution, no fitting.
Chronos tokenizes scaled values and samples paths → any quantile; TimesFM is
a 200M-param decoder pretrained on ~100B time points; Moirai outputs mixture
distributions; Lag-Llama emits Student-t parameters. Open weights; small
checkpoints (Chronos-Bolt, Lag-Llama, Moirai-small) run on CPU in seconds per
series — effectively $0 marginal cost at MO's scale. Realistic expectation on
daily equities: near-random-walk data is their WORST case; a 2026 evaluation
of TimeGPT/TimesFM-2.5/Moirai-2.0/Chronos on liquid US stocks found gains
over random-walk "small and sparse." Expect wide honest intervals and
near-50% directional accuracy — a credible opponent, not an oracle.

**Mechanism candidates for MO:**
- **One zero-shot TSFM as a benchmark agent** (§6 item 2): feed daily closes
  to Chronos-Bolt or Lag-Llama; map its distribution to
  bullish/bearish/neutral via P(return > +θ)/P(< −θ); score in the same
  ledger with the same Brier machinery. Precondition: price pipeline + CPU —
  met.
- Publish the head-to-head: swarm vs TSFM vs random-walk on identical
  resolved questions — whichever way it goes, the finding is publishable and
  on-brand.
- Use TSFM quantile width as a volatility-regime input (wide intervals →
  cap confidence lower). Precondition: item above.

**Not extractable / rejected:** fine-tuning on ASX data (budget; the
financial-returns literature shows negligible payoff); multivariate/covariate
variants (overkill for directional calls); treating the TSFM as an alpha
source — the evidence says it is a benchmark, not an edge.

---

# Appendix A — Mechanism candidates flagged for Phase B extraction

Grouped by how soon the precondition is met. Rubric scoring, kill criteria,
and flag names are Phase B work; this list is the funnel, not the verdict.

**Precondition met TODAY (data already in the ledger):**
1. Spread–error calibration of swarm disagreement (ECMWF) — §6 item 6.
2. Naive / seasonal-naive / exp-smoothing baseline agents (M-comps) — §6 item 1.
3. Climatology-prior agent (Tetlock + M-comps) — §6 item 3; `climatology_probs()` exists.
4. Triple-barrier resolution criteria (López de Prado) — needs only OHLC + EWMA vol.
5. Trials register — log every configuration variant evaluated (López de Prado; cannot be retrofitted later).
6. Per-archetype vs median-ensemble comparison, published (Forecast Hub).
7. Agent correlation screening / pairwise-agreement matrix (WorldQuant; = H2 prerequisite work).
8. Market-relative skill score vs frozen naive drift baseline (syndicates/CLV) — §6 item 4, with the baseline-validation caveat.
9. One zero-shot TSFM benchmark agent (Chronos-Bolt / Lag-Llama) — §6 item 2.
10. "Explain how it loses money" field on the causal-chain audit (Renaissance).
11. Mechanism-class tagging + per-class accuracy attribution (AQR).

**Precondition met after schema work (persist features/distributions):**
12. CRPS + rank histogram on Monte Carlo distributions (ECMWF) — §6 item 5; verify MC distributions are persisted.
13. Conformal sets over {bullish, bearish, neutral} + ACI deployment (Vovk/Gibbs–Candès) — §6 item 8; needs stored per-class probabilities.
14. Adversarial-validation regime-shift alarm (Kaggle) — needs persisted per-prediction feature vectors.

**Precondition is ledger size N (state minimum N; wait for it):**
15. Meta-labeling confidence model (López de Prado) — pooled logistic, 2–4 features, N ≈ 150–300 minimum; purged CV mandatory from day one.
16. Kelly/fractional-Kelly paper-position sizing from ledger-measured edge (Thorp).
17. Reforecast-style per-sector bias correction (ECMWF).
18. WIS scoring (Forecast Hub) — requires quantile/interval outputs first.
19. Deflated-Sharpe / PBO computation (López de Prado) — the REGISTER is item 5 today; the formulas wait for trials and track length.

# Appendix B — Rejection-list seeds (formal write-ups in Phase B)

1. **Extremizing (GJP/Satopää)** — precondition is forecaster independence;
   optimal factor → 1 as information overlap rises; MO's shared-base-model
   swarm would amplify shared bias. Revisit only after H2 delivers
   independent inputs.
2. **Superforecaster selection / inter-agent teaming (GJP)** — agents aren't
   independent samples; discussion risks sycophancy cascades.
3. **Real-money market mechanisms (Metaculus/markets)** — regulatory risk,
   paper-only identity.
4. **AFML data-structures half** (tick/dollar bars, microstructure,
   fractional differentiation, HRP) — presumes tick data and capital.
5. **End-to-end learned market model from the ledger (GraphCast analogy)** —
   sample size is decades away; the flywheel transfers, the model does not.
6. **The 101 alphas as production signals (WorldQuant)** — stylized/expired;
   the shape and harness transfer, the formulas do not.
7. **Fine-tuning a TSFM on ASX data** — negligible measured payoff, real cost.
8. **Trained/weighted ensembles (Forecast Hub)** — need track-record length
   MO lacks; equal-weight median first.
9. **Weighted conformal via likelihood ratios** — fragile at MO's N; ACI
   dominates for this use.
10. **Secrecy as edge (Renaissance/syndicates)** — anti-identity; MO's edge
    is process and proof, not concealment.

# Appendix C — Source-verification note

All citations were gathered by web research on 2026-07-02/03. Book claims
(Zuckerman, Thorp, Tetlock) are cited to the books and secondary reviews.
Before any Phase C/D implementation, the specific numbers relied on in an RFC
(e.g., Satopää extremizing factors, M6 correlation r≈0.04, WIS definition)
must be re-verified against the primary paper, per the Architect Directive's
hostile-auditor standard.
