# Cron Recovery Runbook — `morning_prediction.py`

## Why this exists

As of 2026-05-25, the `prediction_log` shows:
- Total predictions ever: **147**
- Resolved: **68**
- Predictions in last 30 days: **0**
- Last prediction: **2026-04-17**

The 09:30 AEST cron (`schedule = "30 23 * * 0-4"` in `railway.toml`) has
not been firing since 17 April. Without it, the dream-cycle A/B experiment
has no incoming volume to randomise into Treatment and Control arms.

This runbook is the diagnosis-and-fix checklist. Work through it top-down.

## Quick diagnosis (5 minutes)

```bash
# 1. Is the Railway service even running?
railway status
# Look for: deployment status, last deploy timestamp, healthchecks passing

# 2. Has the cron service logged anything recently?
railway logs --service <cron-service-name> --since 7d | head -50
# Expected: a "Morning Pre-Market Run" log line every weekday at 23:30 UTC.
# Likely failure modes: rate limiting, missing env var, network error,
#                       BACKEND_URL pointing somewhere dead.

# 3. Does the backend respond?
curl -sS https://<backend-host>/api/health | jq .
# Expected: status: healthy, environment: production
# If this fails, the cron has nothing to call.
```

## Common causes (ranked by likelihood)

### 1. Railway cron service was paused or deleted

Railway has a separate "service" per cron job. Check the project dashboard:
- Are there two services (backend + cron)? Or has the cron service been removed?
- If removed: recreate it pointing at the same repo, with `railway.toml`
  picking up the `[[cronjobs]]` block. Confirm `MORNING_TICKERS`, `BACKEND_URL`,
  and `API_KEY` env vars are set on the cron service (NOT the backend).

### 2. Missing or expired API key

```bash
railway variables --service <cron-service-name> | grep API_KEY
```

If `MARKET_ORACLE_API_KEYS` on the backend was rotated but the cron's
`API_KEY` was not updated, every cron call returns 401 silently.

Fix: re-set the cron's API_KEY to a value present in the backend's
`MARKET_ORACLE_API_KEYS` comma-separated list.

### 3. Backend rate limit

The cron POSTs `/api/simulate` 6 times (one per ticker) with a 3s pause.
If `slowapi` global limit is 120/min, that's fine — but if the backend was
moved to a stricter limit, calls 3-6 may 429.

Check `backend/server.py` for the `@limiter.limit(...)` decorator on the
simulate route. The default is `120/minute` shared globally; that's enough
for 6 sequential calls.

### 4. `should_block_signals()` is permanently blocking

The simulation route checks data feed health before running. If yfinance has
been unavailable for the entire window, every call fails silently with
`status: failed, error: Data feed unavailable`.

```bash
# Test from local
python -c "
import asyncio, sys; sys.path.insert(0, 'backend')
from monitoring.data_health import should_block_signals
print(asyncio.run(should_block_signals()))
"
```

### 5. Kill switch is active

```bash
curl -sS https://<backend-host>/api/admin/kill-switch -H "X-API-Key: $API_KEY"
```

If `is_active: true`, the cron is returning 503 on every call. Reset via the
admin endpoint (requires the API key).

## Verify the fix

After applying any fix, run the cron manually once to confirm:

```bash
# From local dev or by SSH to the cron service
cd backend && python3 scripts/morning_prediction.py BHP.AX
```

You should see in the log:
```
✅  BHP.AX  →  BULLISH  72.0%  (sim_id: sim_20260525_...)
```

Then check the DB:
```bash
python -c "
import sqlite3
c = sqlite3.connect('backend/aussieintel.db')
for r in c.execute('SELECT id, ticker, predicted_at, experiment_arm FROM prediction_log ORDER BY predicted_at DESC LIMIT 3'):
    print(r)
"
```

You should see a fresh row with a populated `experiment_arm` column (T or C).

## Once volume is restored

The experiment can begin accumulating arm assignments immediately — every row
written through `save_prediction_log` since the 002 migration carries an arm
tag. No additional wiring is needed for the data-collection phase.

The dream-cycle clustering job (not yet built) will read accumulated rows
once N is sufficient. See [analysis_plan.md](./analysis_plan.md) for the
sample-size targets.
