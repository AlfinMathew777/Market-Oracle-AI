---
name: chaos-test
description: Run Market Oracle AI chaos/resilience tests and report failure modes
---

# Chaos Test

Run the chaos and resilience test suite to verify Market Oracle AI degrades gracefully under failure conditions.

## Steps

1. **Run chaos tests with verbose output**

```bash
cd backend && python -m pytest tests/chaos/ -v --tb=short -x
```

2. **Specific failure scenario** (pass as argument: `$ARGUMENTS`)

```bash
cd backend && python -m pytest tests/chaos/test_resilience.py::$ARGUMENTS -v --tb=long
```

3. **Full resilience check including unit tests**

```bash
cd backend && python -m pytest tests/ -v --tb=short -k "resilience or chaos or kill_switch"
```

## What This Tests

| Scenario | What breaks | Expected behaviour |
|---|---|---|
| `TestRedisFailure` | Redis unreachable | Cache miss → live fetch, no exception |
| `TestYFinanceFailure` | yfinance raises | Accuracy checks log warning, return 0 |
| `TestDatabaseFailure` | DB unavailable | Returns empty list / safe zero dict |
| `TestKillSwitchUnderLoad` | Concurrent reads/writes | Kill switch immediately effective |
| `TestLLMTimeout` | LLM hangs | Timeout raised within 5s, no hang |
| `TestConcurrentSimulations` | High parallelism | Semaphore enforces SEM_LIMIT |

## Interpreting Failures

- **PASS** — system degrades gracefully as designed
- **FAIL** — a scenario raised an unhandled exception or hung beyond timeout
- Any FAIL requires investigation before the next deploy

## Manual Chaos Scenarios (Production)

```bash
# Temporarily cut Redis by clearing env var in Railway → verify /api/health shows degraded
# Trigger kill switch via admin UI → verify /api/simulate returns 503
# Revoke API key → verify /api/simulate returns 401
```
