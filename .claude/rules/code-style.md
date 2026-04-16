# Code Style Rules (Market Oracle AI)

Extends `~/.claude/rules/common/coding-style.md` with project-specific rules.

## Python Specifics

### Async/Await
- Use `async/await` for ALL I/O: DB queries, HTTP calls, LLM calls
- Never block the event loop with synchronous I/O
- Use `asyncio.get_event_loop().run_in_executor(None, fn)` for sync libraries (yfinance, FRED)

### Logging
- Use `logging` (stdlib), NOT `print()` or `loguru`
- Module-level logger: `logger = logging.getLogger(__name__)`
- Log level: `INFO` for milestones, `WARNING` for recoverable issues, `ERROR` for failures
- Never log raw API responses — they may contain API keys

### Error Handling
```python
# Always specific exceptions
try:
    price = await fetch_price(ticker)
except Exception as e:
    logger.error("fetch_price failed for %s: %s", ticker, e)
    return None

# Never bare except: with no logging
except:   # ← NEVER DO THIS
    pass
```

### String Formatting
- f-strings for all interpolation
- Never `%` formatting (use only in `logger.xxx(msg, args)` calls — that's correct)
- No `+` concatenation for multi-part strings

### Type Annotations
- All function signatures must have type hints
- `Optional[T]` for nullable return values
- `list[dict]` not `List[Dict]` (Python 3.10+ style)

## Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Files | snake_case.py | `outcome_checker.py` |
| Classes | PascalCase | `AlertChecker` |
| Functions | snake_case | `fetch_price_at_time` |
| Constants | UPPER_SNAKE_CASE | `_VALIDATION_HORIZON_HOURS` |
| Private | _leading_underscore | `_is_duplicate` |
| DB helpers | _leading_underscore | `_fire_alert`, `_insert_alert` |

## File Length

- Route handlers: max 30 lines per endpoint
- Service functions: max 50 lines
- Module total: aim for < 400 lines, hard limit 800 lines
- If a module grows past 400 lines, consider splitting by concern

## Comment Style

Write comments explaining WHY, not WHAT:
```python
# GOOD: Skip weekends — ASX doesn't trade Sat/Sun
if date.weekday() >= 5:
    continue

# BAD: Check if weekend
if date.weekday() >= 5:
    continue
```

## Frontend (React)

- Inline styles for dynamic/conditional values
- CSS files (`.css` co-located) for static layout
- No Redux — use `useState` / `useEffect`
- No React Router — hash-based routing via `window.location.hash`
- Error boundaries around each major panel
