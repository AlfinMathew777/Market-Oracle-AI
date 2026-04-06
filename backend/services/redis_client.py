"""Upstash Redis client — async REST API wrapper.

Replaces all in-memory dict caches. Gracefully no-ops when UPSTASH_REDIS_REST_URL
is not set (local dev falls back to None returns, callers use their own fallback).
"""

import os
import json
import time
import logging
import httpx

logger = logging.getLogger(__name__)

UPSTASH_URL   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_HEADERS = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}


async def cache_get(key: str):
    """Return deserialized value or None if missing/Redis unavailable."""
    if not UPSTASH_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{UPSTASH_URL}/get/{key}", headers=_HEADERS)
            result = r.json().get("result")
            return json.loads(result) if result else None
    except Exception as e:
        logger.warning(f"Redis cache_get({key}) failed: {e}")
        return None


async def cache_set(key: str, value, ttl: int = 3600) -> bool:
    """Serialize value and SET with EX ttl. Also writes seed-meta sidecar key."""
    if not UPSTASH_URL:
        return False
    try:
        payload = [
            ["SET", key, json.dumps(value), "EX", ttl],
            ["SET", f"seed-meta:{key}",
             json.dumps({"fetchedAt": int(time.time() * 1000), "key": key}),
             "EX", ttl * 2],
        ]
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(
                f"{UPSTASH_URL}/pipeline",
                headers={**_HEADERS, "Content-Type": "application/json"},
                json=payload,
            )
            return r.status_code == 200
    except Exception as e:
        logger.warning(f"Redis cache_set({key}) failed: {e}")
        return False


async def cache_get_meta(key: str) -> dict:
    """Return seed-meta for a key: {fetchedAt, key} or empty dict."""
    return await cache_get(f"seed-meta:{key}") or {}


async def acquire_lock(key: str, ttl: int = 60) -> bool:
    """Stampede-protection SET NX. Returns True if lock acquired."""
    if not UPSTASH_URL:
        return True  # always proceed locally
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                f"{UPSTASH_URL}/set/{key}/1/EX/{ttl}/NX",
                headers=_HEADERS,
            )
            return r.json().get("result") == "OK"
    except Exception as e:
        logger.warning(f"Redis acquire_lock({key}) failed: {e}")
        return True  # fail open so seeds still run


async def release_lock(key: str) -> None:
    """Delete a lock key."""
    if not UPSTASH_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            await c.get(f"{UPSTASH_URL}/del/{key}", headers=_HEADERS)
    except Exception as e:
        logger.debug("Redis release_lock failed for %s (best-effort): %s", key, e)


async def incr(key: str, ttl: int = 86400) -> int:
    """Atomic increment with expiry (used for LLM call quotas)."""
    if not UPSTASH_URL:
        return 0
    try:
        payload = [["INCR", key], ["EXPIRE", key, ttl]]
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.post(
                f"{UPSTASH_URL}/pipeline",
                headers={**_HEADERS, "Content-Type": "application/json"},
                json=payload,
            )
            results = r.json()
            return results[0].get("result", 0) if isinstance(results, list) else 0
    except Exception as e:
        logger.warning(f"Redis incr({key}) failed: {e}")
        return 0
