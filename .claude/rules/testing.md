# Testing Rules (Market Oracle AI)

Extends `~/.claude/rules/common/testing.md` with project-specific rules.

## Test Infrastructure

- Framework: **pytest** with `pytest-asyncio` (`asyncio_mode = auto`)
- Location: `backend/tests/`
- Config: `backend/pytest.ini`
- Run: `cd backend && pytest tests/ -v`

## Isolation Requirements

**Production database must never be touched by tests.**

Every test that touches the DB must use the `isolated_db` fixture from `conftest.py`:
```python
async def test_something(isolated_db, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", isolated_db)
    ...
```

The `reset_system_state` fixture is `autouse=True` — kill switch state is
always restored after every test automatically.

## External API Mocking

**Never hit real APIs in tests** — yfinance, FRED, Anthropic, ACLED.

Use the `mock_yfinance` fixture or `unittest.mock.patch`:
```python
def test_price_fetch(mock_yfinance):
    # mock_yfinance already patches yfinance.Ticker
    ...

# Or inline:
with patch("yfinance.Ticker", return_value=mock_ticker):
    ...
```

## Required Tests for Each PR

| Change Type | Required Tests |
|-------------|----------------|
| New endpoint | 1 happy path + 1 error path + 1 auth check |
| Bug fix | Regression test that would have caught the bug |
| New alert type | `_is_duplicate`, `_fire_alert`, check function |
| DB schema change | Migration test (column exists after init_db) |

## Coverage Goals

- `validation/outcome_checker.py`: 90%+ (critical path)
- `monitoring/alerts.py`: 80%+
- `routes/admin.py`: 80%+
- `system_state.py`: 100% (simple state machine, no excuses)

## Test Naming

```python
def test_{unit}_{condition}_{expected_outcome}():
    """Optional: one line explaining what aspect is being tested."""
```

Examples:
```python
def test_determine_outcome_bullish_correct_on_up_move():
def test_kill_switch_returns_503_when_active():
def test_is_duplicate_false_after_cooldown_expires():
```

## Existing Test Files (Do Not Delete)

| File | Covers |
|------|--------|
| `test_circuit_breaker.py` | Infrastructure circuit breaker |
| `test_health_monitor.py` | Agent health monitor |
| `test_orchestrator.py` | Orchestration |
| `test_task_graph.py` | Task graph |
| `test_simulation.py` | Kill switch, paper mode |
| `test_validation.py` | `_determine_outcome`, price fetch |
| `test_alerts.py` | Alert dedup, CRUD |
| `test_admin.py` | Admin endpoints |
| `test_health.py` | Environment module, health shape |
