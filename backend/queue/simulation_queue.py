"""
Redis-backed priority queue for Market Oracle AI simulations.

Architecture:
  API Server  →  enqueue(job)  →  Redis sorted-set  →  Worker dequeues + runs
  Worker      →  complete(result)  →  Redis hash  →  Status endpoint reads

Priority convention: LOWER score = MORE urgent (score 1 = emergency, 10 = batch).
Default priority is 5.

Graceful degradation: if Redis is unavailable or REDIS_URL is not set, all
methods silently no-op and the caller falls back to in-process execution.

Enable via environment: set REDIS_URL and USE_SIMULATION_QUEUE=true.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Queue is only active when both are set:
#   REDIS_URL              — native Redis connection string
#   USE_SIMULATION_QUEUE   — explicit opt-in ("true" / "1" / "yes")
_REDIS_URL = os.getenv("REDIS_URL", "")
_QUEUE_ENABLED_RAW = os.getenv("USE_SIMULATION_QUEUE", "false").lower()
QUEUE_ENABLED: bool = bool(_REDIS_URL) and _QUEUE_ENABLED_RAW in {"true", "1", "yes"}


class SimulationQueue:
    """
    Priority job queue backed by a Redis sorted set.

    Sorted set key:  simulation:jobs          — pending jobs ordered by priority score
    String key:      simulation:processing:*  — jobs currently being executed (TTL 1h)
    String key:      simulation:result:*      — completed/failed results (TTL 24h)
    """

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.redis_url = redis_url or _REDIS_URL or "redis://localhost:6379"
        self._client = None
        self.queue_name        = "simulation:jobs"
        self.results_prefix    = "simulation:result:"
        self.processing_prefix = "simulation:processing:"

    async def connect(self) -> bool:
        """Open Redis connection if not already open. Returns True on success."""
        if self._client is not None:
            return True
        if not _REDIS_URL:
            return False
        try:
            from redis import asyncio as aioredis
            self._client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
            )
            await self._client.ping()
            logger.info("SimulationQueue connected to Redis")
            return True
        except Exception as exc:
            logger.warning("SimulationQueue: Redis connection failed — %s", exc)
            self._client = None
            return False

    async def enqueue(
        self,
        simulation_id: str,
        ticker: str,
        event_data: dict,
        affected_tickers: Optional[list] = None,
        priority: int = 5,
    ) -> str:
        """
        Add a simulation job to the priority queue.

        Args:
            simulation_id: Pre-generated ID (same as used by the API).
            ticker:         Resolved ticker (e.g. "BHP.AX").
            event_data:     Full event dict built by the route handler.
            affected_tickers: User-specified tickers (optional).
            priority:       Lower = more urgent (1 = emergency, 5 = default, 10 = batch).

        Returns:
            simulation_id unchanged (callers use this as the poll key).
        """
        connected = await self.connect()
        if not connected:
            raise RuntimeError("Redis not available — cannot enqueue")

        job = {
            "simulation_id":    simulation_id,
            "ticker":           ticker,
            "event_data":       event_data,
            "affected_tickers": affected_tickers or [],
            "priority":         priority,
            "created_at":       datetime.now(timezone.utc).isoformat(),
            "status":           "queued",
        }

        await self._client.zadd(self.queue_name, {json.dumps(job): priority})
        logger.info("Enqueued simulation %s (ticker=%s priority=%d)", simulation_id, ticker, priority)
        return simulation_id

    async def dequeue(self, timeout: int = 30) -> Optional[dict]:
        """
        Block until a job is available, then return and mark it as processing.

        Uses BZPOPMIN so workers stay idle (no busy-wait) when the queue is empty.
        Returns None on timeout.
        """
        connected = await self.connect()
        if not connected:
            return None

        try:
            # BZPOPMIN returns (queue_name, member_json, score) or None on timeout
            result = await self._client.bzpopmin(self.queue_name, timeout=timeout)
        except Exception as exc:
            logger.warning("SimulationQueue.dequeue error: %s", exc)
            return None

        if not result:
            return None

        _queue_name, job_json, _score = result
        try:
            job = json.loads(job_json)
        except json.JSONDecodeError as exc:
            logger.error("Malformed job JSON in queue: %s — %s", job_json[:200], exc)
            return None

        job["status"]     = "processing"
        job["started_at"] = datetime.now(timezone.utc).isoformat()

        await self._client.set(
            f"{self.processing_prefix}{job['simulation_id']}",
            json.dumps(job),
            ex=3600,   # 1-hour TTL — auto-clears stale in-progress entries
        )
        return job

    async def complete(self, simulation_id: str, result: dict) -> None:
        """Store completed prediction result and remove from processing set."""
        connected = await self.connect()
        if not connected:
            return

        payload = {
            "status":       "completed",
            "result":       result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._client.set(
            f"{self.results_prefix}{simulation_id}",
            json.dumps(payload),
            ex=86400,  # 24-hour TTL
        )
        await self._client.delete(f"{self.processing_prefix}{simulation_id}")
        logger.info("Stored completed result for simulation %s", simulation_id)

    async def fail(self, simulation_id: str, error: str) -> None:
        """Store failure record and remove from processing set."""
        connected = await self.connect()
        if not connected:
            return

        payload = {
            "status":    "failed",
            "error":     error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._client.set(
            f"{self.results_prefix}{simulation_id}",
            json.dumps(payload),
            ex=86400,
        )
        await self._client.delete(f"{self.processing_prefix}{simulation_id}")
        logger.warning("Stored failure for simulation %s: %s", simulation_id, error[:200])

    async def get_result(self, simulation_id: str) -> Optional[dict]:
        """
        Return job status/result dict, or None if the simulation_id is unknown.

        Checks completed/failed results first, then in-progress entries.
        """
        connected = await self.connect()
        if not connected:
            return None

        raw = await self._client.get(f"{self.results_prefix}{simulation_id}")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None

        raw = await self._client.get(f"{self.processing_prefix}{simulation_id}")
        if raw:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None

        return None

    async def get_stats(self) -> dict:
        """Return current queue depth and in-flight job count."""
        connected = await self.connect()
        if not connected:
            return {"enabled": False, "queued": 0, "processing": 0}

        try:
            queued          = await self._client.zcard(self.queue_name)
            processing_keys = await self._client.keys(f"{self.processing_prefix}*")
            return {
                "enabled":    True,
                "queued":     queued,
                "processing": len(processing_keys),
            }
        except Exception as exc:
            logger.warning("SimulationQueue.get_stats failed: %s", exc)
            return {"enabled": True, "queued": 0, "processing": 0, "error": str(exc)}

    async def close(self) -> None:
        """Close the Redis connection gracefully."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None


# Module-level singleton — shared across the API process and imported by workers
queue = SimulationQueue()
