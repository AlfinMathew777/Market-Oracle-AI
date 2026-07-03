# scripts/verify — independent metric reconstruction (Stage 2b)

## Purpose — the Feynman rebuild test

Every published metric family must be recomputable by a hostile auditor from
raw DB rows alone. Each script here rebuilds one family from `prediction_log`
or `reasoning_predictions` and compares it against what the endpoint actually
publishes. This is the constraint-5 remediation from `docs/rfc-worldclass.md`
(§1.7, §4 Stage 2b, §5.1).

## Direction of authority

**Scripts > endpoints.** These scripts recompute metrics from raw rows and are
the source of authority. Endpoints are validated against them, never vice
versa. When a script and an endpoint disagree, the endpoint is the suspect —
the divergence is an andon finding, not a script bug (verify the script
against the spec first, then pull the cord).

## Independence rule

Scripts import **nothing** from `backend/` — stdlib (+ numpy if ever needed)
only. Formulas, token sets, and thresholds are deliberately duplicated:

- deadband ±0.5% with strict inequality (exactly ±0.5 is neutral)
- Wilson 95% interval, z = 1.96; small-sample floor N = 30
- confidence buckets (0–50, 50–60, 60–70, 70–80, 80–90, 90–101)
- 3-class Brier forecast vector (predicted class p = confidence, others split)
- log-loss clip 1e-6, uniform Brier reference 2/3
- 5 equal-count reliability bins, edges `i*N//k`
- direction token sets copied from `validation/direction_normalizer.py`
- validation-summary bands 55–65 / 65–75 / 75–85 / 85%+

If the backend drifts from this spec, the comparison diverges — **that
divergence is the alarm.** Shared code between scripts lives in `_lib.py`
(also backend-import-free).

## How to run

Every script takes `--db PATH` (default `backend/aussieintel.db`, opened
read-only) and at most one of `--endpoint URL` / `--json FILE`:

```bash
cd backend/scripts/verify

# print the reconstruction only
python verify_track_record.py --db ../../aussieintel.db

# compare against the live endpoint
python verify_track_record.py --endpoint https://<host>/api/accuracy/track-record
python verify_calibration.py  --endpoint https://<host>/api/accuracy/calibration
python verify_accuracy_summary.py   --days 90 --endpoint https://<host>/api/accuracy/summary
python verify_validation_summary.py --days 30 --endpoint https://<host>/api/metrics/validation-summary

# compare against a captured response file
python verify_calibration.py --json response.json
```

`--days` on the two summary scripts must match the endpoint query param
(defaults mirror the endpoint defaults: 90 and 30). Time-windowed metrics are
compared seconds apart from the endpoint capture — rows resolving inside that
sliver can produce a transient diff; re-run to confirm.

## Exit-code contract

- `0` — every compared field matches (floats within 1e-6 relative tolerance;
  the reconstruction's fields drive the walk, endpoint prose like `measures`
  and server timestamps like `generated_at` are not compared)
- `1` — mismatch; one structured line per diverging field:
  `path.to.field: recomputed=X endpoint=Y`
- `2` — bad CLI usage (argparse)

Tests in `backend/tests/test_verify_scripts.py` enforce the contract: they
seed an isolated DB, capture the endpoint output in-process, then run each
script as a subprocess and require exit 0.
