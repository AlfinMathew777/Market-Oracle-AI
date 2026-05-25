"""Deterministic Treatment/Control arm assignment for the dream-cycle A/B trial.

Why this module exists
----------------------
Per docs/analysis_plan.md, every prediction is randomly assigned to either the
Treatment arm (receives active lessons via prediction_memory.py) or the Control
arm (identical pipeline, no lesson injection).

Why not Python's built-in hash()
--------------------------------
CPython's hash() is randomised per-process via PYTHONHASHSEED. Two restarts of
the same backend would assign the same (ticker, date) to different arms, which
would silently corrupt the experiment. We use SHA-256 — deterministic across
processes, machines, and Python versions.

Why ticker + date (not timestamp)
---------------------------------
All predictions for the same ticker on the same UTC date land in the same arm.
This means a user clicking "re-run BHP" three times in a day stays in one arm,
which reduces within-cluster variance and is consistent with the morning-cron
volume generator that fires once per ticker per day.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Literal

Arm = Literal["T", "C"]


def _experiment_salt() -> str:
    """Salt the hash so we can re-shuffle if the §3 balance check fails."""
    return os.environ.get("EXPERIMENT_SALT", "dream-cycle-v1")


def assign_arm(ticker: str, predicted_at: datetime | None = None) -> Arm:
    """Return the experiment arm for a prediction.

    Deterministic: the same (ticker, UTC date, salt) tuple always returns the
    same arm. Restart-safe.

    Args:
        ticker:       ASX ticker with .AX suffix.
        predicted_at: UTC timestamp; defaults to now(). Only the date portion
                      is used in the hash.

    Returns:
        "T" (Treatment) or "C" (Control).
    """
    when = predicted_at or datetime.now(timezone.utc)
    date_str = when.strftime("%Y-%m-%d")
    key = f"{ticker}|{date_str}|{_experiment_salt()}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    # First byte mod 2 is uniformly distributed for a cryptographic hash
    return "T" if digest[0] % 2 == 0 else "C"


def prompt_hash(event_data: dict) -> str:
    """Stable hash of the simulation input — lets us detect duplicate runs.

    The full prompt is built deep inside the agent pipeline and not available
    at the persistence site. We hash the event_data payload instead, which is
    the deterministic input that drives the prompt construction.

    Returns the first 16 hex chars of SHA-256 (64-bit truncation — collisions
    are negligible at the volumes we operate at, and full hex would bloat the
    DB needlessly).
    """
    import json

    canonical = json.dumps(event_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
