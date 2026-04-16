"""Global system state: kill switch and paper mode.

Import this module anywhere to read/mutate shared runtime state.
All mutations are in-memory only — restart resets to defaults.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Paper mode ────────────────────────────────────────────────────────────────
# When True: signals are logged normally but NOT published to external webhooks
# (e.g. TradingView). Safe default — requires explicit opt-out.
PAPER_MODE: bool = os.environ.get("PAPER_MODE", "true").lower() != "false"

# ── Kill switch state ─────────────────────────────────────────────────────────
_signals_enabled: bool = True
_kill_switch_reason: Optional[str] = None
_kill_switch_activated_at: Optional[datetime] = None


def is_signals_enabled() -> bool:
    """Return True if the system is allowed to generate signals."""
    return _signals_enabled


def get_system_state() -> dict:
    """Return a snapshot of current system state (safe to include in API responses)."""
    return {
        "signals_enabled": _signals_enabled,
        "kill_switch_active": not _signals_enabled,
        "kill_switch_reason": _kill_switch_reason,
        "kill_switch_activated_at": (
            _kill_switch_activated_at.isoformat() if _kill_switch_activated_at else None
        ),
        "paper_mode": PAPER_MODE,
        "environment": os.environ.get("ENVIRONMENT", "development"),
    }


def activate_kill_switch(reason: str) -> None:
    """Disable signal generation immediately. Thread-safe for single-process deploys."""
    global _signals_enabled, _kill_switch_reason, _kill_switch_activated_at
    _signals_enabled = False
    _kill_switch_reason = reason
    _kill_switch_activated_at = datetime.now(timezone.utc)
    logger.warning("KILL SWITCH ACTIVATED — reason: %s", reason)


def resume_signals() -> None:
    """Re-enable signal generation and clear kill switch state."""
    global _signals_enabled, _kill_switch_reason, _kill_switch_activated_at
    _signals_enabled = True
    _kill_switch_reason = None
    _kill_switch_activated_at = None
    logger.info("Kill switch cleared — signals re-enabled")
