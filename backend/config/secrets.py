"""Secrets management layer for Market Oracle AI.

Provides a unified get_secret() helper that resolves secrets from:

  Priority 1 — Doppler (when DOPPLER_TOKEN is set in the environment)
              Doppler injects secrets as env vars at process start, so in
              practice this is transparent — get_secret() just reads os.environ.

  Priority 2 — Environment variables (Railway, Vercel, local .env.* files)

  Priority 3 — .env file via dotenv (local dev fallback, lowest priority)

Usage:
    from config.secrets import get_secret, require_secret, validate_secrets

    api_key = get_secret("ANTHROPIC_API_KEY")
    db_url  = require_secret("DATABASE_URL")        # raises if missing
    validate_secrets()                              # call at startup

Doppler CLI setup (one-time, dev machine):
    1. Install: https://docs.doppler.com/docs/cli
    2. Login:   doppler login
    3. Setup:   doppler setup          (in project root)
    4. Run:     doppler run -- uvicorn backend.server:app

Railway (staging/prod):
    1. Install Doppler integration in Railway dashboard
       Settings → Integrations → Doppler
    2. All secrets from Doppler project/config are injected automatically.
    3. No DOPPLER_TOKEN needed in Railway — injection is native.

Required secrets (validated at startup):
    ANTHROPIC_API_KEY     — Claude API
    ACLED_EMAIL           — ACLED OAuth
    ACLED_PASSWORD        — ACLED OAuth (or ACLED_API_KEY)
    FRONTEND_URL          — CORS origin

Optional secrets (degraded operation if missing):
    DATABASE_URL          — PostgreSQL (SQLite fallback when absent)
    REDIS_URL             — Deprecated; use UPSTASH_REDIS_REST_URL
    UPSTASH_REDIS_REST_URL    — Upstash REST endpoint
    UPSTASH_REDIS_REST_TOKEN  — Upstash auth token
    FRED_API_KEY          — FRED macro data
    MARKETAUX_API_KEY     — News sentiment
    AISSTREAM_API_KEY     — AIS vessel tracking
    MARKET_ORACLE_API_KEYS    — Comma-separated API keys for /api/reasoning/*
    DOPPLER_TOKEN         — Only needed if calling Doppler API directly
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Required secrets — absence blocks startup ─────────────────────────────────

_REQUIRED_SECRETS = [
    "ANTHROPIC_API_KEY",
    "FRONTEND_URL",
]

# ── Optional secrets — absence is logged but doesn't block startup ────────────

_OPTIONAL_SECRETS = [
    "DATABASE_URL",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "FRED_API_KEY",
    "MARKETAUX_API_KEY",
    "AISSTREAM_API_KEY",
    "ACLED_EMAIL",
    "ACLED_PASSWORD",
    "MARKET_ORACLE_API_KEYS",
]


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Retrieve a secret by name.

    Resolution order:
      1. os.environ (covers Doppler-injected and Railway env vars)
      2. default argument

    Never raises — use require_secret() if you need a hard failure.
    """
    value = os.environ.get(name, default)
    if value is None:
        logger.debug("Secret '%s' not found in environment", name)
    return value


def require_secret(name: str) -> str:
    """
    Retrieve a required secret. Raises RuntimeError if absent.

    Use at startup for secrets that make the application non-functional
    without them (e.g. ANTHROPIC_API_KEY).
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required secret '{name}' is not set. "
            f"Set it via Doppler, Railway environment variables, or .env.{{environment}}."
        )
    return value


def validate_secrets() -> dict:
    """
    Validate all required and optional secrets at startup.

    Returns a dict:
        {
            "required_ok": bool,
            "missing_required": [...],
            "missing_optional": [...],
            "present_optional": [...],
        }

    Logs a clear summary. Does NOT raise — call require_secret() on specific
    keys if you want hard failures.
    """
    missing_required: list[str] = []
    missing_optional: list[str] = []
    present_optional: list[str] = []

    for key in _REQUIRED_SECRETS:
        if not os.environ.get(key):
            missing_required.append(key)

    for key in _OPTIONAL_SECRETS:
        if os.environ.get(key):
            present_optional.append(key)
        else:
            missing_optional.append(key)

    if missing_required:
        logger.error(
            "SECRETS MISSING (required — application may malfunction): %s",
            ", ".join(missing_required),
        )
    else:
        logger.info("All required secrets present: %s", ", ".join(_REQUIRED_SECRETS))

    if missing_optional:
        logger.info(
            "Optional secrets absent (degraded mode): %s",
            ", ".join(missing_optional),
        )

    if present_optional:
        logger.info(
            "Optional secrets configured: %s",
            ", ".join(present_optional),
        )

    return {
        "required_ok": len(missing_required) == 0,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "present_optional": present_optional,
    }


# ── Doppler API direct access (optional, for secret rotation scripts) ─────────

async def fetch_doppler_secret(name: str, project: str, config: str) -> Optional[str]:
    """
    Fetch a secret directly from the Doppler API. Only needed for rotation
    scripts or health checks that verify Doppler is authoritative.

    Requires DOPPLER_TOKEN in the environment.
    Returns None if DOPPLER_TOKEN is not set or the request fails.
    """
    token = os.environ.get("DOPPLER_TOKEN")
    if not token:
        logger.debug("DOPPLER_TOKEN not set — skipping direct Doppler fetch for '%s'", name)
        return None

    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.doppler.com/v3/configs/config/secret",
                params={"project": project, "config": config, "name": name},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("value", {}).get("computed")
            logger.warning(
                "Doppler API returned %s for secret '%s'", resp.status_code, name
            )
    except Exception as exc:
        logger.warning("fetch_doppler_secret failed for '%s': %s", name, exc)

    return None
