"""
Market Oracle AI — Simulation Worker

Pulls jobs from the Redis priority queue and runs the full 50-agent simulation
pipeline, storing results back to Redis for the API server to serve.

Usage:
    python -m workers.simulation_worker            # single worker
    python -m workers.simulation_worker --workers 3  # (future: multi-worker)

Environment:
    REDIS_URL              — Redis connection string (required)
    USE_SIMULATION_QUEUE   — must be "true" (required)
    ANTHROPIC_API_KEY      — for LLM calls
    ENVIRONMENT            — development / staging / production
    PAPER_MODE             — true / false
"""

import asyncio
import logging
import os
import signal
import sys
import types
from datetime import datetime, timezone

# ── Path setup: worker runs from the backend/ directory ──────────────────────
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Bootstrap environment before importing any app modules
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("PAPER_MODE", "false")
os.environ.setdefault("PYTHONUTF8", "1")

from config.logging_setup import setup_logging
setup_logging(env=os.environ.get("ENVIRONMENT", "production"))

logger = logging.getLogger(__name__)


class SimulationWorker:
    """
    Single-process simulation worker.

    Lifecycle:
      1. Connect to Redis queue.
      2. Block on BZPOPMIN — wake only when a job arrives (no busy-wait).
      3. Run the full simulation pipeline (_run_simulation_background).
      4. Read result from the local active_simulations dict (same process).
      5. Write result to Redis for the API server to serve.
      6. Repeat until stopped.

    Shutdown: SIGTERM / SIGINT sets self.running = False so the worker
    finishes the current job then exits cleanly.
    """

    def __init__(self) -> None:
        self.worker_id = f"worker_{os.getpid()}"
        self.running   = False

    async def start(self) -> None:
        from job_queue.simulation_queue import queue

        connected = await queue.connect()
        if not connected:
            logger.error("%s: Redis connection failed — cannot start worker", self.worker_id)
            return

        self.running = True
        logger.info("%s started — waiting for jobs", self.worker_id)

        while self.running:
            try:
                job = await queue.dequeue(timeout=10)
                if job:
                    await self._process(job)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("%s unexpected error: %s", self.worker_id, exc)
                await asyncio.sleep(1)

        logger.info("%s stopped", self.worker_id)

    async def _process(self, job: dict) -> None:
        """Run one simulation job and persist the result to Redis."""
        simulation_id = job["simulation_id"]
        ticker        = job.get("ticker", "UNKNOWN")

        logger.info("%s processing %s (ticker=%s)", self.worker_id, simulation_id, ticker)

        from job_queue.simulation_queue import queue

        try:
            # Reconstruct a minimal body-like object so _run_simulation_background
            # can access body.affected_tickers and body.date without changes.
            body = types.SimpleNamespace(
                affected_tickers=job.get("affected_tickers") or [],
                event_description=job.get("event_data", {}).get("notes", ""),
                event_type=job.get("event_data", {}).get("event_type", ""),
                date=job.get("event_data", {}).get("event_date"),
                lat=job.get("event_data", {}).get("latitude", 0.0),
                lon=job.get("event_data", {}).get("longitude", 0.0),
                country=job.get("event_data", {}).get("country", "Unknown"),
                fatalities=job.get("event_data", {}).get("fatalities", 0),
                event_id=job.get("event_data", {}).get("event_id_cnty"),
            )
            event_data = dict(job.get("event_data", {}))

            # Import the background runner and its in-memory result store.
            # Both live in the same process as this worker, so the update to
            # active_simulations IS visible here (unlike in the API server process).
            from routes.simulate import _run_simulation_background, active_simulations

            # Seed an initial "processing" entry so we can detect stuck workers
            active_simulations[simulation_id] = {
                "status":     "processing",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "worker_id":  self.worker_id,
            }

            # Run the full pipeline — writes completed/failed result into
            # active_simulations[simulation_id] when done
            await _run_simulation_background(simulation_id, body, event_data)

            entry = active_simulations.get(simulation_id, {})
            status = entry.get("status", "failed")

            if status == "completed":
                result_payload = {
                    "status":           "completed",
                    "simulation_id":    simulation_id,
                    "prediction":       entry.get("prediction"),
                    "execution_time":   entry.get("execution_time"),
                    "paper_mode":       entry.get("paper_mode", False),
                    "completed_at":     entry.get("completed_at"),
                    "worker_id":        self.worker_id,
                }
                await queue.complete(simulation_id, result_payload)
                logger.info(
                    "%s completed %s in %.1fs",
                    self.worker_id,
                    simulation_id,
                    entry.get("execution_time", 0),
                )
            else:
                error = entry.get("error", "Unknown error")
                await queue.fail(simulation_id, error)
                logger.warning("%s job %s failed: %s", self.worker_id, simulation_id, error)

        except asyncio.CancelledError:
            await queue.fail(simulation_id, "Worker cancelled during execution")
            raise
        except Exception as exc:
            logger.error(
                "%s job %s raised exception: %s",
                self.worker_id, simulation_id, exc,
                exc_info=True,
            )
            try:
                from job_queue.simulation_queue import queue as _q
                await _q.fail(simulation_id, str(exc))
            except Exception:
                pass

    def stop(self) -> None:
        logger.info("%s stopping after current job completes", self.worker_id)
        self.running = False


async def main() -> None:
    worker = SimulationWorker()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except (NotImplementedError, RuntimeError):
            # Windows doesn't support add_signal_handler for all signals
            signal.signal(sig, lambda _s, _f: worker.stop())

    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
