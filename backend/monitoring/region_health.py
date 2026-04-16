"""
Multi-region health monitoring for Market Oracle AI on Fly.io.

Reports liveness and latency for each deployed region so the admin
dashboard can show failover status and guide traffic decisions.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Region slug → public base URL.
# Add an entry here whenever a new Fly.io region is provisioned.
REGIONS: dict[str, str] = {
    "syd": "https://market-oracle-ai.fly.dev",
    "sin": "https://sin.market-oracle-ai.fly.dev",
}

_HEALTH_TIMEOUT = 5.0   # seconds per region probe


async def check_all_regions() -> dict[str, dict]:
    """
    Probe /api/health on every region concurrently.

    Returns a mapping of region slug → health dict:
        {
            "syd": {"status": "healthy", "latency_ms": 42.1, "http_status": 200},
            "sin": {"status": "unreachable", "error": "Connection refused"},
        }
    """
    import asyncio

    async def _probe(region: str, url: str) -> tuple[str, dict]:
        try:
            async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
                response = await client.get(f"{url}/api/health")
                latency_ms = response.elapsed.total_seconds() * 1000
                healthy = response.status_code == 200
                return region, {
                    "status":     "healthy" if healthy else "unhealthy",
                    "latency_ms": round(latency_ms, 1),
                    "http_status": response.status_code,
                }
        except httpx.TimeoutException:
            return region, {"status": "timeout",     "error": f"No response within {_HEALTH_TIMEOUT}s"}
        except httpx.ConnectError as exc:
            return region, {"status": "unreachable", "error": str(exc)}
        except Exception as exc:
            logger.warning("Region probe failed for %s: %s", region, exc)
            return region, {"status": "error",       "error": str(exc)}

    results = await asyncio.gather(
        *[_probe(region, url) for region, url in REGIONS.items()]
    )
    return dict(results)


def get_current_region() -> str:
    """
    Return the Fly.io region this instance is running in.

    Fly.io injects FLY_REGION automatically; falls back to "local" in dev.
    """
    return os.getenv("FLY_REGION", "local")
