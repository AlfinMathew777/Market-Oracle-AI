"""
API Key Authentication Middleware
----------------------------------
Protects expensive LLM endpoints from unauthorized access.
"""

import hashlib
import logging
import os
import secrets
from typing import Optional

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.status import HTTP_403_FORBIDDEN

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
API_KEY_QUERY = APIKeyQuery(name="api_key", auto_error=False)


def get_api_keys() -> set:
    """
    Load valid API keys from environment.

    Set MARKET_ORACLE_API_KEYS as comma-separated list:
    MARKET_ORACLE_API_KEYS=key1,key2,key3
    """
    keys_str = os.environ.get("MARKET_ORACLE_API_KEYS", "")
    if keys_str:
        return {k.strip() for k in keys_str.split(",") if k.strip()}

    # Auto-generate in dev mode — write key to a local file instead of logging it
    auto_key = os.environ.get("MARKET_ORACLE_AUTO_KEY")
    if not auto_key:
        auto_key = secrets.token_urlsafe(32)
        _key_file = os.path.join(os.path.dirname(__file__), "..", ".dev_api_key")
        try:
            with open(_key_file, "w") as f:
                f.write(auto_key)
            logger.warning(
                "No API keys configured. Dev key written to %s — "
                "set MARKET_ORACLE_API_KEYS in production!",
                os.path.abspath(_key_file),
            )
        except OSError:
            logger.warning(
                "No API keys configured. Set MARKET_ORACLE_API_KEYS in production! "
                "(Could not write dev key file)"
            )

    return {auto_key}


def _hash_key(key: str) -> str:
    """Hash an API key for safe logging (never log raw keys)."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


async def verify_api_key(
    api_key_header: Optional[str] = Security(API_KEY_HEADER),
    api_key_query: Optional[str] = Security(API_KEY_QUERY),
) -> str:
    """
    Verify API key from X-API-Key header or api_key query param.

    Usage in route:
        @router.post("/synthesize")
        async def synthesize(api_key: str = Depends(verify_api_key)):
            ...
    """
    api_key = api_key_header or api_key_query

    if not api_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API key required. Pass via X-API-Key header or api_key query param.",
        )

    if api_key not in get_api_keys():
        logger.warning("Invalid API key attempt: %s", _hash_key(api_key))
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    logger.info("Authenticated request with key: %s", _hash_key(api_key))
    return api_key


async def optional_api_key(
    api_key_header: Optional[str] = Security(API_KEY_HEADER),
    api_key_query: Optional[str] = Security(API_KEY_QUERY),
) -> Optional[str]:
    """
    Optional API key — unauthenticated in dev, required in production.

    Usage:
        @router.get("/summary")
        async def summary(api_key: Optional[str] = Depends(optional_api_key)):
            ...
    """
    api_key = api_key_header or api_key_query

    if not api_key:
        if os.environ.get("ENVIRONMENT") == "production":
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="API key required in production.",
            )
        return None

    if api_key not in get_api_keys():
        logger.warning("Invalid API key attempt: %s", _hash_key(api_key))
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key


def generate_api_key() -> str:
    """Generate a new secure API key."""
    return secrets.token_urlsafe(32)
