# Testing Guide — Market Oracle AI

## Test Categories

| Type | Location | Marker | Speed | Purpose |
|------|----------|--------|-------|---------|
| Unit | `tests/` (top-level) | (none) | Fast | Individual functions, state machines |
| Integration | `tests/integration/` | `@integration` | Medium | Route handlers + DB + service logic |
| E2E | `tests/e2e/` | `@e2e` | Medium | API contract shapes |
| Chaos | `tests/chaos/` | `@chaos` | Slow | Circuit breakers, resilience |
| Load | `tests/load/` | locust | Very slow | Throughput benchmarks |

## Running Tests

```bash
# All tests (unit + integration + e2e + chaos)
cd backend && pytest tests/

# Fast feedback loop — unit tests only, skip slow suites
pytest tests/ -m "not integration and not e2e and not chaos" --ignore=tests/load

# Only integration tests
pytest tests/integration/ -v

# Only e2e contract tests
pytest tests/e2e/ -v

# With full coverage report (opens htmlcov/index.html)
pytest --cov=. --cov-report=html
open htmlcov/index.html   # macOS
start htmlcov/index.html  # Windows

# Run a single file
pytest tests/integration/test_simulation_flow.py -v

# Run a specific test
pytest tests/integration/test_simulation_flow.py::TestKillSwitchGate::test_kill_switch_blocks_simulation -v
```

## Coverage Targets

| Module | Target | Rationale |
|--------|--------|-----------|
| Overall | **85%+** | Gate enforced in CI (`fail_under = 85`) |
| `validation/outcome_checker.py` | 90%+ | Critical path — wrong outcomes corrupt history |
| `monitoring/alerts.py` | 80%+ | Alert dedup bugs cause silent failures |
| `routes/admin.py` | 80%+ | Admin endpoints have high blast radius |
| `system_state.py` | 100% | Simple state machine — no excuses |

## Test Isolation

Every test that touches the database **must** use the `isolated_db` fixture:

```python
async def test_something(isolated_db, monkeypatch):
    monkeypatch.setattr("database.DB_PATH", isolated_db)
    ...
```

The `reset_system_state` fixture is `autouse=True` — kill switch state is always
restored after every test automatically.

## Mocking External Services

**Never hit real APIs in tests** — yfinance, FRED, Anthropic, ACLED.

```python
# yfinance
from unittest.mock import patch, MagicMock

def test_price_fetch(mock_yfinance):
    # mock_yfinance fixture already patches yfinance.Ticker
    ...

# Or inline for one-off mocks:
with patch("yfinance.Ticker", return_value=mock_ticker):
    ...

# Backtest engine data
with patch(
    "backtesting.backtest_engine.fetch_historical_data",
    new_callable=AsyncMock,
    return_value=synthetic_df,
):
    ...
```

## Writing Integration Tests

Integration tests use `httpx.AsyncClient` with `ASGITransport` against mini
FastAPI apps — not the full production server — to avoid heavy startup:

```python
@pytest_asyncio.fixture
async def my_client(isolated_db):
    from routes.simulate import router as simulate_router
    app = FastAPI()
    app.include_router(simulate_router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

The integration conftest provides ready-made fixtures:
- `admin_async_client` — admin routes only
- `simulate_async_client` — simulate + admin routes
- `backtest_async_client` — backtest routes only
- `full_async_client` — simulate + admin + backtest + data routes

## Auth in Tests

`require_api_key` is a no-op when `API_KEY` env var is unset. Integration
and e2e conftest files call `os.environ.pop("API_KEY", None)` to guarantee
this is always the case in test runs.

## CI Coverage Gate

The `coverage-gate` job in `.github/workflows/code-review.yml` runs all tests
and enforces `coverage report --fail-under=85`. A PR that drops coverage below
85% will fail the gate.

## Naming Convention

```python
def test_{unit}_{condition}_{expected_outcome}():
    """One line explaining what aspect is tested."""
```

Examples:
```python
def test_kill_switch_blocks_simulation():
def test_commentary_patterns_are_skipped():
def test_end_before_start_rejected():
def test_backtest_run_creates_run_id():
```
