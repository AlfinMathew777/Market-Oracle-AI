# Dream-Cycle A/B Experiment — Pre-Registered Analysis Plan

> **Status: PRE-REGISTERED.**
> This document defines the metrics, tests, and kill triggers for the
> dream-cycle validation experiment **before** any lessons are activated.
> Once committed, any change to this file must be made by a follow-up PR
> with a new git hash — the original commit hash is the lock.
>
> See `git log -- docs/analysis_plan.md` for the freeze timestamp.

## What this experiment tests

**H1 (primary, two-sided):** Predictions from the Reasoning Synthesizer made
under the Treatment arm (active, human-approved lessons injected via
`prediction_memory.py`) will have a lower Brier score than Control predictions
on the same tickers over the same trading window.

**H0:** `Brier(Treatment) − Brier(Control) = 0`.

## Arms

| Arm | Reasoning Synthesizer input |
|---|---|
| Control (C) | Standard prompt + recent `prediction_log` history. No active lessons. |
| Treatment (T) | Standard prompt + recent history + top-K active lessons from `agent_lessons` where `status='active'` AND `effective_from <= prediction.created_at`. |

- **K = 3** lessons per prompt (frozen for this experiment).
- **Random assignment unit:** the individual prediction row, deterministic by
  `sha256(ticker | UTC_date | EXPERIMENT_SALT)`. See
  `backend/experiment/arm_assignment.py`.
- **Same model, same pipeline, same temperature (0.7 as deployed).** Only the
  lesson-injection block differs.

## Primary metric (the one that decides)

**ΔBrier = Brier(Treatment) − Brier(Control)** with stratified percentile
bootstrap (10,000 resamples, stratified by ticker), 95% CI.

For each resolved prediction, encode `actual_direction ∈ {0,1}` (down/up). The
probabilistic forecast is `p = confidence` if `predicted_direction = 'up'`, else
`p = 1 − confidence`. Brier_i = `(p_i − actual_i)^2`.

Reject H0 if the 95% CI excludes zero on the Brier-decreasing side (i.e.
Treatment better, negative ΔBrier).

Why Brier and not hit-rate: at the ~50% ASX directional baseline, two systems
can have identical hit-rate but very different Brier scores. Brier rewards
calibrated confidence — exactly what lesson injection should improve first.
(Bradley et al. 2008, *Weather and Forecasting*.)

## Secondary metrics (no formal stopping)

1. **Directional hit-rate** — Pesaran–Timmermann (1992) per arm; paired mid-p
   McNemar on `(ticker, date)` overlap rows. If forecast-error autocorrelation
   > 0.15, switch to Pesaran–Timmermann (2009).
2. **Expected Calibration Error (ECE)** — 10 bins on `confidence ∈ [0.5, 1.0]`,
   reliability diagram per arm, bootstrap CI on ΔECE.
3. **Log loss** per arm, complements Brier.
4. **Hit-rate by sector**, Holm-Bonferroni corrected.
5. **Diebold–Mariano with HLN small-sample correction** on log-loss differential
   (only when N per arm > 50).

## Sample size

| MDE on hit-rate (vs 50%) | Required N per arm |
|---|---|
| 55% (5pp lift) | ~620 |
| 53% (3pp lift) | ~1,720 |
| 52% (2pp lift) | ~3,900 |

**Target: N ≥ 1,200 per arm.** Given the current event-driven traffic level
(0 predictions in the trailing 30 days as of pre-registration), this requires
either restored cron volume (see [cron_recovery_runbook.md](./cron_recovery_runbook.md))
or extended runtime. **Do not unblind early to compensate for low N.**

## Kill conditions (auto-revert)

A single SQL `UPDATE agent_lessons SET status='inactive'` fires if **any** of:

| # | Trigger | Threshold |
|---|---|---|
| 1 | Brier degradation | `Brier_T − Brier_C > 0.02` over rolling 5-trading-day window AND bootstrap 95% CI excludes 0 in the harmful direction |
| 2 | Hit-rate floor | Treatment hit-rate < 0.45 over last 100 Treatment predictions |
| 3 | Sequential futility (SPRT) | Cumulative log-LR on log-loss differential crosses `log(β/(1−α)) = log(0.20/0.95) ≈ −1.56` for α=0.05, β=0.20 |
| 4 | Model fingerprint change | LLMRouter primary model identifier changes mid-experiment |
| 5 | Model fallback rate | > 5% of Treatment-window predictions served by a fallback tier (not configured primary) |
| 6 | Manual | Human reviewer flips any individual lesson's `status` to `inactive` via admin endpoint |

> **Note on SPRT boundary:** The boundary is `log(β/(1−α))`. For α=0.05, β=0.20
> that's `log(0.2/0.95) ≈ −1.56`, *not* `log(α/(1−α)) ≈ −2.94`. An earlier draft
> swapped α and β — fixed here before lock.

## Anti-leakage guard (non-negotiable)

Every lesson row carries an `effective_from` timestamp. The injection query in
`prediction_memory.py` MUST include:

```sql
WHERE status = 'active'
  AND effective_from <= :prediction_created_at
  AND (sector = :sector OR sector IS NULL)
ORDER BY priority DESC LIMIT 3;
```

A daily integrity check asserts no `agent_lessons` row has been used on any
`prediction_log` row whose `predicted_at` predates the lesson's `effective_from`.
**This guard exists before the lesson generator is built so it cannot be
forgotten.**

## What's blinded

The human reviewer who approves dream-cycle lessons in the `agent_lessons`
queue does NOT see arm-level metrics during the experiment window. This
prevents the approval gate from becoming an unblinded judge.

## Frozen choices (changing requires a follow-up PR)

- Primary metric: ΔBrier (stratified bootstrap 95% CI, 10,000 resamples).
- K (lessons per prompt): 3.
- Random unit: prediction row, hashed by `(ticker, UTC_date, EXPERIMENT_SALT)`.
- Temperature: 0.7 (as-deployed; measure the live system, not an idealisation).
- Lesson scope filter: `sector OR NULL` (no ticker-specific lessons activated).
- Kill triggers and their thresholds: as listed above.
- Sample target: N ≥ 1,200 per arm.

## What's NOT frozen (engineering still in flight)

- The dream cycle clustering job itself — not yet implemented.
- The lesson generation prompt — not yet implemented.
- Model-used capture (currently logs configured primary, not actually-used).

These will land in follow-up PRs. Each PR that materially changes the
experiment surface area must update this document.

## References

Full literature scaffolding (Reflexion, Voyager, MemGPT, DSPy, BloombergGPT,
FinMem, Aronson, Pesaran–Timmermann, Bradley et al., ASIC REP 798) lives in
the longer design memo this plan was distilled from. The references are not
re-copied here because that memo is the audit artefact; this file is the lock.
