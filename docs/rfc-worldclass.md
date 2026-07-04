# RFC: World-Class Directive — Market Oracle AI

Status: DRAFT — Phase 0 complete, awaiting approval.
Branch: feat/superforecaster-loop. Method: 4 parallel read-only inventory
agents (routes, services, trust, infra) with grep-level caller-graph evidence.
Nothing has been deleted or modified. This document is the deletion proposal.

---

## 1. Phase 0 — Deletion pass

### 1.1 Surface surveyed

| Domain | Items | KEEP | ORPHANED | SUSPECT/dup | TEST-ONLY |
|---|---|---|---|---|---|
| HTTP/WS endpoints | 63 | 34 | 24 | 5 | — |
| services/agents/quant modules | 60 | 59 | 1 | 3 dup clusters | 0 |
| trust/validation/monitoring/config | 40 | 38 | 0 | 1 legacy | 1 |
| infrastructure/orchestration/queue/data_sources/db | 13 | 8 | 1 | 2 conditional | 3 |
| scripts/ | 14 | 4 | 8 (+1 artifact) | — | 1 |
| env vars / flags | ~45 | ~24 | 13 orphan knobs | 3 anomalies | 1 |
| repo-root artifacts | 12 | 0 | 12 | — | — |
| **Total surveyed** | **~247** | | | | |

Ground truth established during survey: `scripts/test_core.py` is the live
simulation engine (imported by `routes/simulate.py:357`); `trust/` is live via
`routes/{simulate,reasoning,accuracy}`; deploy story is Railway + Vercel
(CLAUDE.md canonical); SQLite default with optional Postgres via `db/connection.py`
(NOT a duplicate of `database.py` — driver shim vs data layer).

### 1.2 Requirements with no owner (Musk step 1)

Surface that exists with no traceable reason (no commit rationale, no doc, no
caller, no measured need):

1. Three deploy targets (Railway + Render + Fly) for one system. Only Railway
   is canonical. `deploy-fly.yml` still ACTIVELY deploys on push to main.
2. Two backtest systems (`services/backtester.py` vs `backtesting/backtest_engine.py`).
3. Two prediction-history endpoints, three accuracy endpoints, two calibration
   endpoints, two news aggregators, ten health probes (3 with consumers).
4. Two parallel API-key implementations (`server.py` inline vs `middleware/auth.py`).
5. An orchestration state machine (`orchestration/`) nothing instantiates.
6. A/B experiment arms assigned on every simulation while treatment == control
   (self-documented no-op).
7. 13 env knobs nothing can set; `ANTHROPIC_API_KEY` validated-as-required but
   consumed by no code path; `ACLED_API_KEY` documented but never read;
   `WORKER_TYPE` set but never read.
8. Emergent-era artifacts (`.emergent/`, `backend_test.py`, `test_result.md`,
   `test_reports/`, `.gitconfig`, `plan.md`) from the abandoned scaffold platform.

### 1.3 Deletion proposal — Tier 1 (zero live callers, zero coupling — delete)

Repo root (12 items): `.emergent/`, `memory/` (root, empty), `ais-relay/`,
`backend_test.py`, `test_result.md`, `plan.md`, `render.yaml`, `fly.toml`,
`fly.worker.toml`, `Dockerfile.worker`, `test_reports/`, `.gitconfig`.
Coupled: `.github/workflows/deploy-fly.yml` (must go with fly.toml or CI keeps
deploying to a non-canonical target).

Scripts (8 + 1 artifact): `seed_bank_memory.py`, `seed_memory.py`,
`test_llm_quick.py`, `test_poc_simple.py`, `poc_output_20260315_013502.json`,
`seed_acled.py`, `seed_asx_prices.py` (render-only crons; services fall back to
direct API), `auto_tune_agents.py` (unreferenced; its confidence replay has
already diverged from production). `seed_macro.py` goes with render.yaml.

Modules (5): `integration/prediction_pipeline.py` (zero refs — orphans the
package), `infrastructure/context_manager.py` (zero refs anywhere),
`infrastructure/inference_client.py`, `orchestration/orchestrator.py`,
`orchestration/task_graph.py` (test-only cluster; delete with their test files
`test_orchestrator.py`, `test_task_graph.py`, `test_context_budget.py` stays —
it tests `services/context_budget`, a different live module).

Endpoints (21): `/api/health/infrastructure`, `/api/accuracy/{evaluation,
failure-analysis,health}`, `/api/admin/check-alerts`, `/api/admin/regions`,
`/api/data/{gdelt-sentiment,mineral-deposits,rba,health}`,
`/api/data/alt-data/{health,sample}`, `/api/news/asx/{categories,tickers}`,
`/api/predictions/{log,backtest,admin/fix-data,calibration}`,
`/api/simulate/active`, `/api/predict/accuracy`, `/api/stream/health`,
`/api/trade/health`.
NOT deleted despite orphan status: `/api/accuracy/track-record` and
`/api/accuracy/calibration` — these are the audit interface (Stage 7 gate and
the Feynman surface). Their orphanhood is the problem H5 fixes, not evidence
of uselessness.

Env/config hygiene: remove `ANTHROPIC_API_KEY` from `_REQUIRED_SECRETS`
(consumed nowhere), remove `ACLED_API_KEY` from docs/templates (never read),
`MARKET_ORACLE_AUTO_KEY` hook, `LLM_CONCURRENCY`/`DEBUG_TIMINGS`/
`TRUST_LEDGER_DB` orphan knobs (hardcode current defaults),
`GUARDIAN/FINNHUB/GNEWS/ALPHA_VANTAGE` key reads + their dead branches,
`REDDIT_CLIENT_ID/SECRET` + `data_sources/reddit_sentiment.py` (permanently
dormant, returns []).

### 1.4 Deletion proposal — Tier 2 (live-code consolidation — delete after tests)

1. `services/backtester.py` + its `/api/predictions/backtest` endpoint —
   consolidate on `backtesting/backtest_engine.py` (has Sharpe/drawdown; the
   only one with schema + status polling).
2. `monitoring/region_health.py` + `/api/admin/regions` — Fly.io region probes
   on a Railway deploy; `get_current_region()` always returns "local".
3. Dual auth: migrate `routes/admin.py` from `server.py`-inline
   `require_api_key` to `middleware/auth.py`; delete the inline copy and the
   legacy `API_KEY` mechanism (one auth path, one env var).
4. Accuracy surface: `/api/predict/history` vs `/api/predictions/history` —
   both frontend-called; consolidate frontend on one, delete the other (one
   sitting of frontend work; done under paired verification).

### 1.5 Deferred — explicitly NOT deleted, with reasons and kill criteria

1. `trust/evidence_trail.py` (test-only): raw material for H4 (epistemic
   provenance graph). Kill criterion: if H4 is rejected in Phase 1 ranking,
   this module is deleted in the same PR that closes the RFC.
2. `job_queue/` + `workers/simulation_worker.py`: live code path in
   routes/simulate.py, flag default-off, but nothing on Railway starts a
   worker (only the deleted Fly config did). Kill criterion: if no Railway
   worker service exists by the time Phase 3 flight-readiness runs, delete the
   queue path, the worker, and `USE_SIMULATION_QUEUE` in one commit.
3. `experiment/arm_assignment.py`: no-op arms, but the pre-registration
   machinery (deterministic salt-hashed assignment) is exactly what H5 needs.
   Reuse or delete at Phase 1 ranking.
4. Orphan-but-ours flags `USE_BELIEVABILITY_WEIGHTS`,
   `ENABLE_NEWS_RELEVANCE_FILTER`, `MC_SIMULATIONS`/`MC_CONFIDENCE_SIMS`:
   fix is to make them settable (add to .env templates + Railway docs), not
   delete — they gate real, tested code.

### 1.6 Doc-drift corrections (bundled with Tier 1)

- README documents `/api/admin/system-status` (actual: `/api/admin/status`).
- README documents `/ws/stream` (actual: `/api/stream/prices`).
- `config/secrets.py` marks `REDIS_URL` deprecated while the queue requires it.
- CLAUDE.md says "PostgreSQL" plainly; actual: SQLite default, PG optional.

### 1.7 Measured fact for later phases (not a deletion)

Feynman gap: **9 of 10 published metric families have no independent
reconstruction script.** `scripts/verify/` does not exist. The only
reconstruction-adjacent script is `revalidate_historical.py` (labels only).
This is the largest single violation of the "provable to a hostile auditor"
definition and is Phase 2's primary candidate regardless of H1–H7 ranking.

### 1.8 Deletion arithmetic

Tier 1 + Tier 2 remove: 13 root/CI artifacts + 9 scripts + 6 modules +
22 endpoints + ~12 env knobs/branches ≈ **62 of ~247 surveyed items ≈ 25%**
of surface area — comfortably above the 10% mandate. Estimated LOC removed:
~4,500–6,000 (endpoints + modules + scripts + configs), against ~1,600 LOC of
moat-bearing code added in the last two branches. Moat-per-line moves in the
right direction by construction.

### 1.9 Phase 0 approval record (2026-07-03)

APPROVED WITH AMENDMENTS. Tier 1 + Tier 2 as scoped, subject to:

1. 14–30 day access-log check on all 24 orphaned endpoints before deletion,
   plus deployed-frontend-vs-HEAD check (the deployed Vercel bundle may call
   endpoints the current source does not).
2. Platform decommissioning, not file deletion: destroy the Fly app, verify
   Render cron reality, then delete configs.
3. Confirm health-probe consumers include platform-level healthchecks
   (Railway healthcheckPath, uptime monitors) before deleting any probe.
4. Validated-but-unconsumed API keys are security findings: rotate/remove the
   live secrets (`ANTHROPIC_API_KEY`, `ACLED_API_KEY`) from Railway/Doppler,
   not just from code.
5. Deletion PR requires replay regression green + explicit confirmation of no
   import-time side effects lost (deleted modules must not have been doing
   work at import).
6. The published backtest result (47.5% hit rate, Sharpe −1.63) must remain
   reproducible after backtest dedup.
7. One commit per deletion cluster.

Ruling: `scripts/verify/` is compliance remediation, not a hypothesis —
excluded from Phase 1 ranking. Revised sequence: **Phase 2a** deletions →
**Phase 2b** verify scripts for surviving metrics → **Phase 2c** rank-#1
hypothesis. Separate PRs.

---

## 2. Phase 1 — Hypothesis evaluation

Method: each hypothesis scored 1–5 on the rubric (Compounds with N /
Unfakeable / Complexity cost, 5 = trivial / Deletion potential / Thesis
alignment), with a falsifiable claim, a killing measurement, and a flag name.
Evidence base: the four Phase 0 inventories, the consensus/accuracy audits,
and the GJP/aggregation research brief (all in session record). Constraint
context that shapes every score: **N is small, the last backtest showed no
edge, and per-archetype all-sides vote attribution only began accruing with
commit e8bcf5d** — anything needing per-agent history starts from ~zero data.

### 2.1 Rubric table

| H | Proposal | Compounds | Unfakeable | Complexity | Deletion | Thesis | Σ | Status |
|---|---|---|---|---|---|---|---|---|
| **H5** | Pre-registered falsification page | 5 | 5 | 4 | 3 | 4 | **21** | **RANK #1** |
| H7 | Honest extremizing | 5 | 5 | 4 | 1 | 4 | 19 | BLOCKED (needs H2 + N≥100) |
| H2 | Correlation-aware aggregation | 5 | 4 | 3 | 2 | 4 | 18 | Rank #2 |
| H4 | Epistemic provenance graph | 3 | 5 | 2 | 3 | 4 | 17 | Rank #3 |
| H3 | Regime-conditional calibration | 4 | 4 | 3 | 1 | 3 | 15 | Rank #4 |
| H1 | Adversarial self-play league | 3 | 4 | 1 | 1 | 5 | 14 | Flagship, deferred |
| H6 | Shadow-council audit | 2 | 3 | 4 | 1 | 3 | 13 | Rank #6 |

### 2.2 Per-hypothesis verdicts

**H5 — Pre-registered public falsification page. RANK #1.**
- Falsifiable claim: pre-committing thresholds to the ledger BEFORE outcomes
  arrive, and publishing results unchanged either way, measurably increases
  external credibility at zero risk to honesty — and no retroactive fake is
  possible because the commitment hash precedes the data.
- Kill measurement: none applicable (pure verification infrastructure — the
  directive itself exempts it).
- Flag: `ENABLE_FALSIFICATION_PAGE` (read-only page; flag gates publication).
- Why #1: cheapest item on the board; converts the system's honest "no edge
  yet" status — its most distinctive property — into public, unfakeable
  credibility; gives the two orphaned audit endpoints
  (`/api/accuracy/track-record`, `/api/accuracy/calibration`) their consumer;
  reuses `experiment/arm_assignment.py`'s deterministic salt-hash machinery
  (resolving that module's deferred-deletion status: REUSED, not deleted).
- Scope note (fork-test hardening, folded in rather than a new hypothesis):
  each pre-registration entry and each published snapshot includes the ledger
  chain-head hash, and the page lives in the repo so GitHub commit history
  externally timestamps it. This closes the fork test's main hole (§4.4): a
  hash chain proves internal consistency, not external time; commits anchor
  the chain head outside the author's control.
- Pre-registered thresholds to sign first (drafted, adjustable at Phase 2c
  review, immutable after signing): "At N=150 resolved directional
  predictions, publish BSS vs per-ticker climatology with bootstrap 95% CI,
  unchanged, whether or not the CI clears 0" and "If BSS CI does not clear 0
  by N=300, the headline page states the system has no demonstrated edge."

**H7 — Honest extremizing. Score 19, but BLOCKED by its own definition**
(fit on holdout, only after H2, only at N≥100). Not eligible for rank #1
now; becomes cheap once H2 exists.
- Falsifiable claim: fitted a ≠ 1.0 improves holdout Brier beyond bootstrap
  noise. Expected honest outcome for a correlated LLM ensemble: a ≤ 1
  (de-extremizing) — publishing that is itself credibility.
- Kill: holdout improvement within bootstrap noise → ship a = 1.0, say so
  publicly. Flag: `EXTREMIZE_A` (float, default 1.0 = identity).

**H2 — Correlation-aware aggregation. Rank #2.**
- Falsifiable claim: weighting archetype votes by unique information
  (inverse error-correlation) yields lower paired Brier than raw-count
  aggregation on the same predictions.
- Kill: no paired-Brier improvement at N≈100 resolved.
- Flag: `USE_DIVERSITY_WEIGHTS` (composes with `USE_BELIEVABILITY_WEIGHTS`;
  both confidence-arithmetic-only, raw counts untouched — same insertion
  discipline as e8bcf5d).
- Data honesty: with 4 archetypes the error-correlation matrix is 4×4 —
  estimable early, but coarse. All-sides attribution began accruing
  yesterday; the matrix needs ~50+ resolved predictions before it is anything
  but prior. Building it now means paired logging from prediction #1
  (constraint 3) with weights held at identity until the estimate stabilizes.
- Sequencing: prerequisite to H7; the paired-logging harness it needs is the
  same harness H5's snapshots read. H2 follows H5 naturally.

**H4 — Epistemic provenance graph. Rank #3.**
- Falsifiable claim: every number on a published prediction is reachable by
  walking hash-chained ledger entries alone (measured: a walker script
  reconstructs the prediction's trust certificate, votes, weights, and
  reputation inputs with zero DB joins outside the ledger).
- Kill: none (read-only verification), but strictly read-only scope.
- Flag: `ENABLE_PROVENANCE_API` (read-only endpoint; UI later).
- Resolves `trust/evidence_trail.py` deferred deletion: REVIVED as the
  walker's core. Complexity honest-scored at 2: the backend walk is cheap,
  the UI is not; Phase 2c scope would be endpoint-only.

**H3 — Regime-conditional calibration. Rank #4.**
- Falsifiable claim: BSS differs across realized-vol terciles by more than
  bootstrap noise (the system is measurably better in some regimes).
- Kill: auto-defer per bucket below minimum N; publish the deferral.
- Flag: none needed (pure read-side extension of `/api/accuracy/calibration`).
- Deferred behind H5/H2 because at current N every bucket auto-defers — it
  ships as three empty buckets. Cheap to add when N justifies it.

**H1 — Adversarial self-play league. Flagship, deferred — and that is the
Musk-order answer, not a demotion.**
- Falsifiable claim: gateway catch-rate against red-team attack classes shows
  a positive learning trend over tournament rounds, auditable from ledger
  entries alone.
- Kill (as given): red agents cannot produce attacks distinguishable from
  random noise after a fixed round budget, OR no learning trend → freeze the
  league, document why.
- Flag: `ENABLE_REDTEAM_LEAGUE` (staging only, ever).
- Why deferred despite Thesis=5: Simons rule (§3.4 of the directive) — when
  choosing between a smarter mechanism and a better measurement, take the
  measurement. The league's own value claim ("the trust stack's improvement
  is a graphable curve") is unprovable until the measurement substrate (H5's
  published snapshots, Phase 2b's verify scripts) exists. Building the league
  first would produce an unfalsifiable shrine. It is the correct Phase 3+
  flagship, entered through a flight-readiness review, once its curve has
  something rigorous to be plotted against. Complexity=1 is honest: new agent
  framework, tournament state, LLM budget, new ledger entry types.

**H6 — Shadow-council external audit. Rank #6.**
- Falsifiable claim: multi-model council review of postmortems + calibration
  snapshots yields actionable findings a single-model review missed.
- Kill (as given): two consecutive audits with zero actionable findings →
  reduce cadence. Flag: none (offline script, not runtime).
- Deferred: there are no postmortem artifacts yet (docs/postmortems/ does not
  exist — the andon-cord mechanism that feeds it is itself unbuilt). H6
  without inputs is a committee reviewing an empty folder.

### 2.3 No new hypotheses proposed

The one candidate considered (external time-anchoring of the ledger head) is
folded into H5's scope, where it belongs — a separate mechanism would be a
new invariant surface for zero additional moat.

---

## 3. Required Phase 1 questions

### 3.1 What breaks at 10× agents (250–500)?

1. `get_persona_distribution` hard-asserts totals == 25 — crashes outright.
2. Diversity does NOT scale: 4 archetypes on one base model means 10× agents
   adds 10× correlated votes, not 10× information. `calculate_confidence`'s
   √participation factor would inflate confidence with zero new signal —
   exactly the correlated-ensemble failure H2 measures. Agent count is a
   cost knob, not a quality knob; this is measurable today via H2's
   correlation matrix.
3. LLM semaphore (10–20 concurrent) makes wall-clock linear in agents;
   rate-limit ceilings on Groq free tiers arrive well before 250.
4. Monte Carlo bootstrap and reconciler prompt size scale linearly.
Conclusion: 10× agents is strictly negative expected value until H2 proves
marginal votes carry unique information. The directive's 45–50 number is
already past the knee.

### 3.2 Smallest system with the same moat

Ledger (hash chain + replay) + resolver (outcome writer) + `trust/scoring.py`
+ pre-registration entries + one public read endpoint + `scripts/verify/`.
Roughly 10 files. Everything else — 50 agents, 5 gateway layers, Monte Carlo,
chokepoint models — is signal-generation apparatus that the moat *measures*
but does not consist of. This is the sharpest formulation of why Phase 2a
(deletion) and 2b (verify scripts) precede any hypothesis: they shrink the
system toward its moat kernel.

### 3.3 What would Renaissance delete?

The agent-count arms race (see 3.1); every unscored judgment surface — the
gateway layers emit vetoes and confidence caps that are never scored against
outcomes (Tetlock-rule violation, noted as an open item for a future H1
prerequisite: score gateway decisions like any other forecast); the news/UX
surface that never feeds a scored prediction; and both backtest systems in
favour of one walk-forward harness whose numbers ship with reconstruction
scripts. They would keep: the ledger, the resolvers, the deadband, the
paired-logging discipline, and the honesty about Sharpe −1.63.

### 3.4 Fork test verdict

A competitor forking the repo today gets: all code, all prompts, the
constitution, the trust stack. They do NOT get: (a) the resolved prediction
history with hash-chained provenance rooted in real, externally observable
time; (b) reputation/believability state earned from live outcomes; (c) any
fitted parameters (extremizing a, diversity weights) once H2/H7 exist —
those are functions of the private outcome history. Residual weakness: the
hash chain alone proves internal consistency, not external time — a forker
could fabricate a plausible history offline. H5 closes this by anchoring
chain-head hashes in GitHub commit history (externally timestamped) with
every pre-registration and snapshot. Verdict after H5: PASS — the moat is
accumulated, verified, externally anchored history. Verdict today: PARTIAL.

---

## 4. Staged plan (per Phase 0 amendments)

| Stage | Content | Gate |
|---|---|---|
| 2a | Tier 1 + Tier 2 deletions, one commit per cluster | Amendments 1–7 checklist below; replay regression green |
| 2b | `scripts/verify/` reconstruction for every SURVIVING metric family (~6 after dedup: track-record, calibration/Brier suite, accuracy summary, validation summary, backtest Sharpe/drawdown, quant VaR/CVaR), CI job comparing against live endpoint output | Byte-match (within float tolerance) endpoint vs reconstruction |
| 2c | H5 only: pre-registration ledger entry type, threshold signing, public page reading track-record + calibration endpoints, chain-head anchoring | Flight-readiness review (Phase 3 checklist) before flag ON in staging |
| 3+ | H2 (paired logging first, weights identity) → H7 (post-H2, N≥100) → H4 endpoint → H3 buckets → H1 league via flight-readiness → H6 once postmortems exist | Each behind its flag, each with kill criterion armed |

### 4.1 Amendment compliance checklist for Stage 2a (all must be evidenced in the PR)

- [ ] Access-log query covering ≥14 days shows zero hits on each endpoint
      deleted (Railway logs; if logs unavailable, deploy a 410-logging stub
      first and wait the window).
- [ ] Deployed Vercel bundle grepped for deleted paths (build artifact, not
      source).
- [ ] Fly app destroyed (`fly apps destroy`), Render dashboard checked for
      live crons, THEN configs deleted.
- [ ] Railway healthcheckPath and any uptime monitors confirmed pointing only
      at `/api/health`.
- [ ] `ANTHROPIC_API_KEY` / `ACLED_API_KEY` rotated or removed in
      Railway/Doppler (security finding, not cleanup).
- [ ] Import-time side-effect review: each deleted module read for top-level
      work (none found in Phase 0 reads; re-verify at PR).
- [ ] Backtest 47.5% / Sharpe −1.63 re-run reproduced on the surviving engine
      before the duplicate is deleted.
- [ ] Replay regression green; one commit per cluster.

---

*Phase 1 ends here. No implementation code has been written. Next action on
approval: Stage 2a deletion PR (respecting the access-log window), or — since
the log window imposes a 14–30 day wait — Stage 2b verify scripts may proceed
in parallel on a separate branch, as they touch no deleted surface.*

---

## 5. Phase 1 approval record (2026-07-03)

APPROVED WITH AMENDMENTS. Ranking and staging accepted: 2b now (parallel),
2a after the log window, 2c = H5. Five amendments:

1. **Anchoring:** server- or blockchain-timestamped proofs only —
   OpenTimestamps or RFC-3161 — never git commit dates (client-supplied,
   forgeable). Proof files committed to the repo; anchor-verification script
   in `scripts/verify/`; any new dependency needs its constraint-6 paragraph.
2. **Verify-script direction of authority:** scripts recompute metrics from
   raw ledger/DB rows and are endpoint-agnostic. Endpoints are validated
   against scripts, never vice versa. During the 2a log window, run the
   scripts against ALL duplicate endpoints; any divergence between duplicates
   is an andon finding and becomes input to the 2a dedup decision (which
   duplicate was wrong, not just which is unused).
3. **First anchored pre-registrations (2c):** (a) BSS-vs-climatology
   thresholds at N=50 and N=150, publish-either-way; (b) the paired
   believability-weights analysis plan, anchored BEFORE
   `USE_BELIEVABILITY_WEIGHTS` ever flips on.
4. **Fork-test language:** post-H5 verdict is "PASS on fabricability,
   PENDING on magnitude" — anchoring proves the history is real, not that
   the edge is large. Magnitude comes only from N and BSS.
5. **H1 addendum:** the self-play league doubles as the labeling engine that
   resolves the gateway Tetlock violation (§3.3) — red-team rounds generate
   ground-truth-labeled attack/clean traffic, making gateway vetoes scorable
   for the first time. Logged as H1 scope, strengthening its Phase 3+ case.
   The 25-persona hard-assert (§3.1) is a KNOWN LIMIT, recorded here;
   no drive-by fix.

### 5.1 Stage 2b scope note (metric families and honest exclusions)

In scope (recomputable from raw persisted rows): track-record (hit rate,
Wilson CI, baseline, horizons), calibration suite (Brier, log loss, BSS,
ECE, Murphy, bins), accuracy summary, validation summary (band accuracy),
backtest (Sharpe, drawdown, hit rate from stored backtest_predictions).

Excluded with justification: quant VaR/CVaR/Monte Carlo — computed on the
fly from live market data, never persisted; not reconstructible "from raw
ledger entries" by definition. The constraint-5 obligation for quant is
property-testing (already covered in tests/), not ledger reconstruction.
The anchor-verification script is 2c scope (nothing to verify until the
first proof exists).

Independence rule: verify scripts import NOTHING from backend/ — formulas
and thresholds (deadband 0.5, Wilson z=1.96, confidence caps) are
deliberately duplicated. If the backend drifts from the spec, the scripts
diverge and that divergence is the alarm. stdlib + numpy only.

### 5.2 Stage 2b andon findings (2026-07-03 — reported, not fixed; ruling required)

The independence rule caught five defects in SURVIVING endpoints before any
production run. Per amendment 2, endpoints are validated against scripts —
each finding implies an endpoint correction that would change published
numbers, so none was applied as a drive-by. Ruling requested at the 2b stop.

| # | Finding | Severity | Implication |
|---|---|---|---|
| A1 | `trust/track_record.fetch_resolved_rows` does not filter `excluded_from_stats`; every other stats surface does. Resolved garbage rows count in the published track record AND the calibration suite. | HIGH | The Stage 7 gate metric and the H5 headline metric are contaminated by design. Fix before 2c. |
| A2 | validation-summary publishes `SUM(prediction_correct)` as-is while track-record re-derives labels (the column is documented as distrusted). Seeded proof: a lying flag counts correct in one endpoint, incorrect in the other. | HIGH | Two surviving endpoints can publish contradictory hit rates from the same rows. |
| A3 | validation-summary drops only the literal `'neutral'` token; legacy aliases (`flat`, `hold`, `sideways`) and junk tokens flow into hit rate and `by_direction`. | MEDIUM | Hit-rate denominator inflated by abstentions. |
| A4 | accuracy-summary windows on naive local `datetime.now()`; validation-summary uses UTC; SQLite space-separated vs isoformat `T` string comparisons skew window edges by up to the UTC offset. | MEDIUM | Same-day metrics differ by server timezone. |
| A5 | Docs pointed validation-summary at `database.get_detailed_accuracy_stats`; actual source is `outcome_checker.get_validation_summary`. | LOW | Doc drift only; scripts reconstruct the real source. |

Proposed disposition (pending ruling): A1+A2 fixed in a dedicated
`fix:` PR on the 2b branch BEFORE 2c (H5 must not anchor a contaminated
metric), with paired before/after values logged for any prediction already
resolved; A3+A4 fixed in the same PR if approved; A5 bundled with Tier 1
doc-drift corrections in 2a.

Duplicate-endpoint sweep status: `verify_duplicates.py` ready; the live
sweep against staging runs during the 2a log window (exit 2 = DIVERGE =
andon artifact in docs/postmortems/). The accuracy cluster is EXPECTED to
diverge — three endpoints read three different tables (simulations,
prediction_log, reasoning_predictions); the sweep will quantify it for the
2a dedup decision.

### 5.3 Phase C partial rulings record (2026-07-03)

Owner rulings received; recorded verbatim in effect:

1. **DNS outage** — postmortem stub opened
   (`docs/postmortems/2026-07-03-dns-outage.md`); root cause pending owner
   dashboard check. **The Stage 2a access-log window clock starts only after
   restoration plus 48h of stable traffic.** Stage 2a is frozen until then.
2. **Accuracy divergence ruled** — the sweep was executed 2026-07-03 against
   a locally-served copy of snapshot `e16532e` (9.5% / 53.5% / 31.0%;
   `docs/analyses/2026-07-03-duplicate-endpoint-divergence.md`). Canonical
   accuracy endpoint = **`/api/accuracy/summary`** (the byte-match
   survivor). `/api/predict/accuracy` and `/api/predictions/accuracy` are
   deprecated in 2a; the semantic cause of each number is named in
   `docs/postmortems/2026-07-03-accuracy-divergence.md` (pre-deletion
   requirement satisfied). **A1–A5 are fixed FORWARD on the survivor and
   track-record family only** — §5.2's proposed disposition is amended
   accordingly (no fixes to endpoints already marked for deprecation).
3. **Reputation provenance audit executed**
   (`docs/analyses/2026-07-03-reputation-provenance-audit.md`): Feynman-test
   FAILURE recorded for the reputation/believability family — attribution
   evidence is persisted by design (hash-chained ledger, archetype_votes)
   but no reconstruction script exists and no reachable DB can demonstrate a
   rebuild. `USE_BELIEVABILITY_WEIGHTS` and all H2/H7 believability
   experiments are FROZEN until schema v2 accumulates data and
   `verify_reputation.py` has replayed real ledger evidence.
4. **Trials-register anchoring** — register head OpenTimestamps-stamped
   (proofs in `docs/trials/anchors/`), decoupled from the H5 page build per
   ruling 7; amendment-1 anchoring machinery is thereby partially in service
   ahead of 2c.
5. Phase D remains gated on owner verdict + production restoration. No
   Phase D code has been written.

### 5.4 A6–A9 resolver audit (2026-07-04 rulings; reported, fixes queued in A-series)

Audit question (ruling 1): horizon-dated or fetch-time prices for expired
rows? Verdict differs per path:

| # | Finding | Severity | Detail |
|---|---|---|---|
| A6 | `database.run_accuracy_checks` (simulations/24h family) resolves with **fetch-time prices**: `fast_info.last_price` vs `previous_close` — i.e., the one-day move of WHATEVER DAY the job runs, regardless of prediction date. An expired backlog row gets an outcome unrelated to its window. All 147 simulation outcomes (the 9.5% number) were produced by this rule. | **HIGH** | Fix in the A-series pattern. Until fixed, simulation outcomes are not protocol-valid evidence for anything. |
| A6-pass | `outcome_checker.validate_prediction` and `services/prediction_resolver` both use **horizon-dated historical windows** (entry = first close ≥ prediction date, exit = first close ≥ prediction date + horizon). Late resolution yields correct labels. | — | The 2026-07-03 mid-sweep resolutions carry valid labels. |
| A7 | **Resolution as an unconditional startup side effect**: `server.py` `_boot_cleanup()` runs `auto_resolve_pending_predictions(limit=200)` at every boot in EVERY environment, plus `_hourly_tasks` in-process. This is what mutated the sweep's scratch DB. | **HIGH (process)** | Standing rule (ruling 1, recorded): resolution is an explicit, logged job — never a startup side effect; dev boot defaults no-resolve; all verify/sweep tooling runs read-only. Code fix queued in A-series. |
| A8 | `prediction_resolver` labels say "over 7 trading days" but implements +7 CALENDAR days snapped to the next trading close; entry price is the PREDICTION-DAY close even for intraday predictions (hours of entry-price look-ahead). | LOW | This paragraph is now the precise definition of resolution protocol v2; fix the label text, not the math, unless re-registered. |
| A9 | **Resolution is not write-once.** `prediction_resolver` selects `WHERE prediction_correct IS NULL`, but resolved-NEUTRAL rows keep `prediction_correct=NULL` by design — so all 56 neutral rows re-qualify and get `actual_*`, `resolved_at`, `resolution_notes` OVERWRITTEN on every boot and hourly tick. The 2026-07-03 sweep boot touched 79 rows: 23 genuinely pending + 56 re-resolved neutrals. Deterministic horizon-dated math makes the rewrite usually value-identical, but the ledger surface churns and any manual correction would be silently clobbered. | **HIGH (ledger integrity)** | Fix: select on `actual_direction IS NULL` (the true unresolved marker) + write-once guard on resolution fields. A-series. |

Quarantine executed (ruling 2): all 79 rows touched by the dev-boot
resolver are marked `excluded_from_stats=1` with reason code
`A7_STARTUP_SIDE_EFFECT_RESOLUTION` — in the session's scratch artifact
only. **Production was never touched** (it is unreachable); there is
nothing to quarantine in any ledger of record. The pristine snapshot used
by the analysis lane was never mutated, so no published analysis is
contaminated.

Cron/hostname blast radius (ruling 3): resolution does NOT ride public
DNS — it runs in-process (`_hourly_tasks`, `_boot_cleanup`) inside the
backend service. The only Railway cron (`railway.toml`, morning
predictions) calls `$BACKEND_URL`, documented as the `*.railway.app`
internal hostname, not the custom domain — set in the dashboard, so
unverifiable from the repo. Consequence: **if the Railway service is
healthy, the DNS outage did NOT stop resolution or (probably) morning
predictions — it silenced the public API/frontend and blinded external
observation.** Whether the service IS healthy, and whether resolutions
have continued since April, only the owner's dashboard can answer — that
answer is also the sealed-verdict flip condition for Phase D ordering.
