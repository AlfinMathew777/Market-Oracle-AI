# Security Rules (Market Oracle AI)

Extends `~/.claude/rules/common/security.md` with project-specific rules.

## Protected Files (Hook-Enforced)

The `file-protection.sh` pre-tool hook blocks editing:

| Pattern | Why Protected |
|---------|---------------|
| `.env` (exact, no suffix) | Real secrets — API keys, auth tokens |
| `backend/aussieintel.db` | Production prediction data |
| `railway.toml` | Production deployment config |
| `vercel.json` | Frontend deployment config |

Template files `.env.development`, `.env.staging`, `.env.production` are
**not** protected — they contain only placeholder comments.

## API Key Rotation Log

If a key is exposed in git history, rotate it immediately:

| Date | Key | Action Required |
|------|-----|-----------------|
| 2026-04-06 | EMERGENT_LLM_KEY (sk-emergent-9EfCeA20...) | Rotated |
| 2026-04-06 | FRED_API_KEY (845738...) | Rotate at fred.stlouisfed.org |
| 2026-04-06 | MARKETAUX_API_KEY (UNZzV1IH...) | Rotate at marketaux.com |

## Admin Endpoint Auth Pattern

All mutation endpoints use `require_api_key(request)`:
```python
from server import require_api_key
require_api_key(request)  # Raises HTTP 401 if invalid key
```

Key is set via `MARKET_ORACLE_API_KEYS` (comma-separated for rotation support).
In dev without `API_KEY` set → open access (intentional, dev convenience).

## AFSL / Financial Advice

Market Oracle AI is NOT a licensed financial advisor.

- Outputs are **predictions** — probabilistic, not advice
- Never use: "buy", "sell", "invest", "recommend"
- Always frame as: "The model predicts...", "Historical accuracy shows..."
- Do not add disclaimers to every response — they're in the frontend UI

## Environment Variable Safety

```python
# Always .get() with a default — never os.environ["KEY"]
# That crashes startup if missing
value = os.environ.get("MY_VAR", "")

# Required vars should fail loud with a clear message:
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    logger.warning("ANTHROPIC_API_KEY not set — LLM calls will fail")
```

## Rate Limiting

All endpoints are rate-limited via `slowapi` at 120/min globally.
LLM endpoints have stricter per-endpoint limits (10/min).
Never remove rate limiting from any endpoint.

## CORS

Production CORS is locked to `https://asx.marketoracle.ai`.
Wildcard `*` is blocked in production by `server.py` even if set in env.
