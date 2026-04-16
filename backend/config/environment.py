"""Environment configuration for Market Oracle AI.

Loads the correct .env file based on the ENVIRONMENT variable:
  development  → .env.development  (local dev, hot reload, verbose logging)
  staging      → .env.staging      (pre-prod, real data, paper mode on)
  production   → .env.production   (Railway prod, paper mode off by default)

Usage:
    from config.environment import ENV, is_production, is_staging, is_development
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Valid environments ─────────────────────────────────────────────────────────

_VALID_ENVIRONMENTS = {"development", "staging", "production"}
_DEFAULT_ENVIRONMENT = "development"

# ── Resolve environment ────────────────────────────────────────────────────────

ENV: str = os.environ.get("ENVIRONMENT", _DEFAULT_ENVIRONMENT).lower().strip()

if ENV not in _VALID_ENVIRONMENTS:
    logger.warning(
        "[ENV] Unknown ENVIRONMENT=%r — falling back to %r. "
        "Valid values: %s",
        ENV,
        _DEFAULT_ENVIRONMENT,
        ", ".join(sorted(_VALID_ENVIRONMENTS)),
    )
    ENV = _DEFAULT_ENVIRONMENT

# ── Load environment-specific .env file ───────────────────────────────────────

_BACKEND_ROOT = Path(__file__).parent.parent
_ENV_FILE = _BACKEND_ROOT / f".env.{ENV}"

try:
    from dotenv import load_dotenv

    if _ENV_FILE.exists():
        load_dotenv(_ENV_FILE, override=False)  # Don't override vars already set in shell
        logger.debug("[ENV] Loaded %s", _ENV_FILE.name)
    else:
        # Fallback to generic .env if the env-specific file doesn't exist
        _fallback = _BACKEND_ROOT / ".env"
        if _fallback.exists():
            load_dotenv(_fallback, override=False)
            logger.debug("[ENV] %s not found — loaded .env fallback", _ENV_FILE.name)
        else:
            logger.debug("[ENV] No .env file found for environment %r", ENV)
except ImportError:
    logger.debug("[ENV] python-dotenv not installed — skipping .env load")


# ── Convenience helpers ────────────────────────────────────────────────────────

def is_development() -> bool:
    """Return True when running in the local development environment."""
    return ENV == "development"


def is_staging() -> bool:
    """Return True when running in the Railway staging environment."""
    return ENV == "staging"


def is_production() -> bool:
    """Return True when running in the Railway production environment."""
    return ENV == "production"


# ── Startup banner ─────────────────────────────────────────────────────────────

def log_environment_banner() -> None:
    """Log a prominent banner showing the active environment.

    Call this once during application startup (e.g. inside FastAPI lifespan).
    """
    _banners = {
        "development": "[ENV] Running in DEVELOPMENT mode — hot reload, verbose logging",
        "staging":     "[ENV] Running in STAGING mode — pre-prod, paper mode on",
        "production":  "[ENV] Running in PRODUCTION mode",
    }
    banner = _banners.get(ENV, f"[ENV] Running in {ENV.upper()} mode")

    if ENV == "production":
        logger.info(banner)
    elif ENV == "staging":
        logger.warning(banner)
    else:
        logger.info(banner)
