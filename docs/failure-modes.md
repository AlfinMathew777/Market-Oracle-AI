# Failure Modes & Resilience — Market Oracle AI

## Design Principles

1. **Fail open on reads** — a failing cache or data feed returns `None`/`[]`, never an exception surfaced to the user.
2. **Fail closed on writes** — failed DB writes are logged at ERROR and dropped. The simulation result is still returned to the user.
3. **Kill switch is always available** — even if the LLM pipeline is stuck, the kill switch endpoint `/api/admin/kill-switch` must respond within 1s.
4. **Never panic on missing optional secrets** — `FRED_API_KEY`, `MARKETAUX_API_KEY`, `AISSTREAM_API_KEY` absent → degraded mode, not crash.

---

## Failure Catalogue

### Redis Unavailable

| Trigger | `UPSTASH_REDIS_REST_URL` not set, or network unreachable |
|---|---|
| Behaviour | `cache_get()` returns `None`, `cache_set()` returns `False` |
| Fallback | Service fetches live data on every request |
| User impact | Slower responses; higher upstream API usage |
| Detection | `GET /api/health → data_sources.Redis.status = "UNAVAILABLE"` |
| Resolution | Restore Upstash credentials in Railway env vars |

### PostgreSQL Unavailable (DATABASE_URL set)

| Trigger | `DATABASE_URL` set but DB unreachable |
|---|---|
| Behaviour | `init_db()` raises at startup; Railway restarts the container |
| Fallback | None — PG is required when DATABASE_URL is set |
| Detection | Railway crash loop; logs show `asyncpg.PostgresConnectionError` |
| Resolution | Check Railway PostgreSQL add-on status / DATABASE_URL value |

### SQLite (default) — Disk Full

| Trigger | `/data` partition exhausted |
|---|---|
| Behaviour | `save_simulation()` logs ERROR and swallows — prediction still returned |
| Fallback | In-memory results only (lost on restart) |
| Detection | `backend.log` shows `Failed to save simulation` |
| Resolution | Clear old data or expand Railway persistent disk |

### yfinance Rate-Limited / Down

| Trigger | Yahoo Finance blocks the request |
|---|---|
| Behaviour | `run_accuracy_checks()` catches and logs; returns 0 checked |
| Fallback | PENDING outcomes stay PENDING until next check cycle |
| Detection | Logs: `Accuracy check failed for {ticker}: rate limited` |
| Resolution | Automatic — next scheduled check runs in 24h |

### LLM API Unavailable

| Trigger | `ANTHROPIC_API_KEY` invalid / Anthropic outage |
|---|---|
| Behaviour | `LLMRouter` raises after timeout; simulation returns error |
| Fallback | Gemini fallback attempted (via LLMRouter circuit breaker) |
| Detection | `GET /api/health → llm_circuits` shows open circuit |
| Resolution | Check Anthropic status page; rotate key if needed |

### ACLED / News Feed Down

| Trigger | ACLED API rate-limited or credentials invalid |
|---|---|
| Behaviour | Falls back to RSS events; then demo GeoJSON |
| Detection | `/api/data/acled → source: "demo"` |
| Resolution | Check `ACLED_EMAIL`/`ACLED_PASSWORD` in Railway env vars |

### Kill Switch Triggered

| Trigger | Manual via `/api/admin/kill-switch` or `check_all_alerts()` |
|---|---|
| Behaviour | All `/api/simulate` calls return 503 immediately |
| Detection | `GET /api/admin/status → kill_switch_active: true` |
| Resolution | `POST /api/admin/resume` |

### High Signal Volume (> 10/hour)

| Trigger | More than 10 non-excluded signals generated in 60 min |
|---|---|
| Behaviour | `HIGH_SIGNAL_VOLUME` alert created (warning); simulation continues |
| Detection | Active alerts dashboard; Railway logs |
| Resolution | Monitor for data feed loop; consider temporary kill switch |

### ML Anomaly Detected

| Trigger | IsolationForest flags unusual pattern in last 10 signals |
|---|---|
| Behaviour | `ML_ANOMALY` alert created (warning); simulation continues |
| Detection | Active alerts dashboard |
| Resolution | Review recent predictions for hallucination or data contamination |

---

## Runbook: Complete Degradation Recovery

```bash
# 1. Check system status
curl https://asx.marketoracle.ai/api/health | jq .

# 2. Check active alerts
curl -H "X-API-Key: $KEY" https://asx.marketoracle.ai/api/admin/alerts

# 3. If kill switch is active, resume
curl -X POST -H "X-API-Key: $KEY" \
     https://asx.marketoracle.ai/api/admin/resume \
     -d '{"reason": "manual recovery"}'

# 4. Verify health after resume
curl https://asx.marketoracle.ai/api/health | jq .status
```

---

## Chaos Test Execution

```bash
# Run full resilience suite (CI)
cd backend && python -m pytest tests/chaos/ -v --tb=short

# Run specific scenario
cd backend && python -m pytest tests/chaos/test_resilience.py::TestRedisFailure -v
```

See [performance.md](performance.md) for load test setup.
