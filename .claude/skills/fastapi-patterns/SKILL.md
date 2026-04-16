---
description: FastAPI best practices for Market Oracle AI backend. Trigger when creating endpoints, handling async operations, or structuring API responses.
globs:
  - "backend/**/*.py"
---

# FastAPI Patterns Skill

## Standard API Response Shape
```python
# All endpoints return:
{"status": "success" | "error", "data": ..., "message": "..."}

# Error responses
{"detail": "user-friendly message"}   # FastAPI HTTPException format
```

## Endpoint Pattern (30-line max)
```python
@router.post("/api/resource")
async def create_resource(body: ResourceRequest, request: Request):
    """One-line docstring."""
    from server import require_api_key
    require_api_key(request)

    result = await service_function(body.field)
    if result is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    return {"status": "success", "data": result}
```

## Kill Switch Gate Pattern
```python
from system_state import is_signals_enabled, get_system_state

if not is_signals_enabled():
    state = get_system_state()
    raise HTTPException(
        status_code=503,
        detail={
            "error": "System paused — signal generation disabled",
            "reason": state["kill_switch_reason"],
        },
    )
```

## Background Task Pattern
```python
import asyncio

# Fire-and-forget (no result needed)
asyncio.create_task(check_all_alerts())

# Polled background simulation (use active_simulations dict)
async def _run_simulation_background(simulation_id: str, ...):
    try:
        active_simulations[simulation_id]["status"] = "running"
        result = await run_the_work()
        active_simulations[simulation_id].update({"status": "complete", "result": result})
    except Exception as e:
        active_simulations[simulation_id].update({"status": "failed", "error": str(e)})
```

## Auth Pattern
```python
# In admin endpoints — sync check, raises on failure
from server import require_api_key
require_api_key(request)

# API key is set via MARKET_ORACLE_API_KEYS env var (comma-separated)
# Unset in dev → all requests pass (open access)
```

## Middleware (SecurityHeadersMiddleware)
- Already adds: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`
- Also adds: `X-Environment` (from `config.environment.ENV`)
- Do NOT add a second middleware — extend the existing one in `server.py`

## Rate Limiting
```python
# Slowapi — already configured globally at 120/minute
# Per-endpoint override:
from slowapi import Limiter
@limiter.limit("10/minute")
async def expensive_endpoint(request: Request): ...
```

## Paper Mode Check
```python
from system_state import PAPER_MODE

if PAPER_MODE:
    logger.info("[PAPER] Would have published: %s %s @ %.0f%%", direction, ticker, conf * 100)
else:
    await publish_signal(...)   # Live publishing
```

## Environment Variable Access
```python
# Always use .get() with a sensible default — never os.environ["KEY"]
# That raises KeyError if missing, which crashes startup
value = os.environ.get("MY_VAR", "default")

# Exception: at startup validation (intentional crash on missing required vars)
```

## Health Check Additions
When adding a new data source, add it to `/api/health` in `server.py`
alongside the existing `check_fred`, `check_yfinance` etc. pattern.

## Key Files

| File | Purpose |
|------|---------|
| `backend/server.py` | App factory, lifespan, middleware, health |
| `backend/routes/admin.py` | Kill switch, status, alerts, validation trigger |
| `backend/routes/simulate.py` | Main simulation pipeline |
| `backend/system_state.py` | PAPER_MODE, kill switch state |
| `backend/config/environment.py` | ENV, is_staging(), log_environment_banner() |
| `backend/monitoring/data_health.py` | Feed staleness gate |
| `backend/monitoring/alerts.py` | 5 alert types, check_all_alerts() |
