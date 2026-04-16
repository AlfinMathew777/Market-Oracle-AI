Quick system health check — returns status of all critical components.

## Usage
```
/health-check
```

## What This Checks

| Check | Endpoint | Pass Condition |
|-------|----------|----------------|
| Kill switch | `/api/admin/status` | `signals_enabled: true` |
| Paper mode | `/api/admin/status` | Report current value |
| Environment | `/api/admin/status` | Report current environment |
| Data feeds | `/api/health/data-feeds` | `signals_blocked: false` |
| yfinance | `/api/health` | `data_sources.yfinance.status: OK` |
| FRED | `/api/health` | `status: OK or PENDING_KEY` |
| Active alerts | `/api/alerts` | 0 critical unacknowledged |
| Recent accuracy | `/api/metrics/validation-summary?days=7` | `hit_rate > 0.50` |

## Commands to Run
```bash
curl http://localhost:8000/api/admin/status
curl http://localhost:8000/api/health
curl http://localhost:8000/api/health/data-feeds
curl http://localhost:8000/api/alerts?status=active
curl "http://localhost:8000/api/metrics/validation-summary?days=7"
```

## Quick Fix Suggestions

| Issue | Fix |
|-------|-----|
| Kill switch active | `POST /api/admin/resume` with `{"confirm": true}` |
| Data feed stale | Check yfinance/FRED connectivity; restart backend if needed |
| Critical alert | `POST /api/alerts/{id}/acknowledge` after investigating |
| Hit rate < 50% | Check accuracy drop alert; review recent predictions for logic errors |
