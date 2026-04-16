# Performance Benchmarks — Market Oracle AI

## SLO Targets

| Endpoint | p50 Target | p95 Target | Error Rate |
|---|---|---|---|
| `GET /api/health` | < 200ms | < 500ms | < 1% |
| `GET /api/data/acled` | < 300ms | < 1s | < 2% |
| `GET /api/data/asx-prices` | < 500ms | < 2s | < 2% |
| `GET /api/data/chokepoints` | < 200ms | < 800ms | < 1% |
| `GET /api/data/prediction-history` | < 400ms | < 1.5s | < 2% |
| `GET /api/quant/accuracy` | < 500ms | < 2s | < 2% |
| `POST /api/simulate` | < 15s | < 30s | < 5% |

## Running Load Tests

### Local (against dev server)

```bash
# Start backend
cd backend && uvicorn server:app --reload --port 8000

# Install locust
pip install locust==2.24.0

# Run interactive UI
locust -f backend/tests/load/locustfile.py --host http://localhost:8000
# Open http://localhost:8089 → set users=10, spawn=2, host=localhost:8000

# Run headless (30s quick smoke test)
locust -f backend/tests/load/locustfile.py --host http://localhost:8000 \
       --headless -u 10 -r 2 -t 30s
```

### Against Staging

```bash
export LOAD_TEST_API_KEY="your-staging-api-key"

locust -f backend/tests/load/locustfile.py \
       --host https://staging.asx.marketoracle.ai \
       --headless -u 50 -r 5 -t 5m \
       --html docs/load-report.html
```

### Via GitHub Actions

1. Go to **Actions → Load Test — Market Oracle AI**
2. Click **Run workflow**
3. Set `target_host`, `users`, `spawn_rate`, `duration`
4. Download the HTML report from artifacts after completion

Automated runs execute every weekday at 01:00 UTC against staging.

## User Class Breakdown

| Class | Weight | Wait | Purpose |
|---|---|---|---|
| `ReadOnlyUser` | 7x | 1-3s | Health + data endpoints (dashboard consumers) |
| `AnalyticsUser` | 2x | 2-5s | Accuracy + history (power users) |
| `SimulationUser` | 1x | 10-30s | /api/simulate (deliberate usage) |

## Caching Strategy

Market Oracle AI uses a two-tier cache:

| Layer | Backend | TTL | Scope |
|---|---|---|---|
| L1 | Upstash Redis (REST) | 5 min (prices), 1h (macro) | All Railway instances |
| L2 | In-memory dict | Session-scoped | Per-process fallback |

Cache hit rates can be observed via `GET /api/health → data_sources.Redis`.

## Historical Benchmarks

Populate this table after each load test run.

| Date | Users | p50 (simulate) | p95 (simulate) | Error Rate |
|---|---|---|---|---|
| 2026-04-16 | baseline | — | — | — |
