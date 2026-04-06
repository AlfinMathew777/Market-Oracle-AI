"""
Per-Endpoint Rate Limiting
---------------------------
Supplements app-level slowapi with per-client limits on expensive LLM routes.
In-memory store — fine for single Railway instance. Use Redis for multi-instance.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

logger = logging.getLogger(__name__)

# (requests, window_seconds) per endpoint type
_LIMITS: Dict[str, Tuple[int, int]] = {
    "llm":     (10, 60),   # 10 req/min — expensive LLM calls
    "search":  (30, 60),   # 30 req/min — data fetch endpoints
    "default": (100, 60),  # 100 req/min — everything else
}


class _RateLimiter:
    def __init__(self) -> None:
        # client_id → list of request timestamps
        self._requests: Dict[str, list] = defaultdict(list)

    def _client_id(self, request: Request, api_key: Optional[str]) -> str:
        if api_key:
            return f"key:{api_key[:12]}"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"
        return f"ip:{request.client.host}"

    def check(
        self,
        request: Request,
        endpoint_type: str = "default",
        api_key: Optional[str] = None,
    ) -> dict:
        """
        Check rate limit. Returns info dict with limit/remaining/reset_in.
        Raises HTTP 429 when limit is exceeded.
        """
        max_req, window = _LIMITS.get(endpoint_type, _LIMITS["default"])
        client_id = self._client_id(request, api_key)

        now = time.time()
        # Evict timestamps outside the window
        self._requests[client_id] = [
            ts for ts in self._requests[client_id] if now - ts < window
        ]

        count = len(self._requests[client_id])
        if count >= max_req:
            oldest = min(self._requests[client_id])
            reset_in = int(window - (now - oldest))
            logger.warning(
                "Rate limit exceeded for %s: %d/%d (endpoint=%s)",
                client_id, count, max_req, endpoint_type,
            )
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry in {reset_in}s.",
                headers={
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_in),
                },
            )

        self._requests[client_id].append(now)
        return {
            "limit": max_req,
            "remaining": max_req - count - 1,
            "reset_in": window,
        }

    @staticmethod
    def headers(info: dict) -> dict:
        return {
            "X-RateLimit-Limit": str(info["limit"]),
            "X-RateLimit-Remaining": str(info["remaining"]),
            "X-RateLimit-Reset": str(info["reset_in"]),
        }


# Module-level singleton
rate_limiter = _RateLimiter()


async def llm_rate_limit(request: Request, api_key: Optional[str] = None) -> dict:
    """
    FastAPI dependency for LLM endpoint rate limiting (10 req/min).

    Usage:
        @router.post("/synthesize")
        async def synthesize(
            rate_info: dict = Depends(llm_rate_limit),
            api_key: str = Depends(verify_api_key),
        ):
            ...
    """
    return rate_limiter.check(request, endpoint_type="llm", api_key=api_key)
