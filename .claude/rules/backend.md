---
paths:
  - "backend/**/*.py"
---

# Backend Rules — Market Oracle AI

## Framework
- FastAPI. Routes in `backend/routes/`. Services in `backend/services/`.
- All endpoints rate-limited via `slowapi`. Never remove rate limiting.
- Pydantic models for all request/response shapes. No raw dicts as API contracts.

## Services Architecture
- Business logic lives in `services/`, not in route handlers
- Route handlers: validate input → call service → return response. Max 30 lines.
- Services are stateless functions or classes with no side effects in `__init__`

## Database
- SQLite via `database.py`. Never raw string SQL — use parameterized queries.
- All DB operations in try/except with proper rollback on failure

## Caching
- Redis via `cache.py`. TTL always set explicitly — never cache without expiry.
- Cache keys namespaced: `"resource:identifier:version"` format

## AI/LLM Calls
- All Claude API calls go through `LLMRouter`. Never call `anthropic` client directly.
- Timeout on every LLM call. Retry logic max 2 attempts.
- Log token usage for cost tracking.

## Error Handling
- Never expose Python stack traces to API responses
- `logger.error(msg, exc_info=True)` for unexpected errors
- Return `{"detail": "user-friendly message"}` with appropriate HTTP status

## Secrets
- All secrets via env vars. Never hardcode. Check `os.environ.get()` not `os.environ[]`
  (the latter raises KeyError on missing — use `.get()` with a clear error message)
