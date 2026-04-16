"""Admin endpoints for Market Oracle AI.

All mutation endpoints (kill-switch, resume, acknowledge) require API key auth.
Read-only status/health endpoints are unauthenticated for monitoring dashboards.

Endpoints:
    POST /api/admin/kill-switch           — disable all signal generation
    POST /api/admin/resume                — re-enable signal generation
    GET  /api/admin/status                — current system state
    GET  /api/health/data-feeds           — live data feed health + signal-block status
    POST /api/admin/validate-predictions  — manually trigger 24h outcome validation
    POST /api/admin/check-alerts          — manually trigger all alert checks
    GET  /api/metrics/validation-summary  — accuracy breakdown by band / direction
    GET  /api/alerts                      — alert history (active or all)
    POST /api/alerts/{id}/acknowledge     — mark an alert as acknowledged
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from system_state import activate_kill_switch, get_system_state, is_signals_enabled, resume_signals

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])


# ── Request models ─────────────────────────────────────────────────────────────

class KillSwitchRequest(BaseModel):
    reason: str


class ResumeRequest(BaseModel):
    confirm: bool


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/api/admin/kill-switch")
async def kill_switch(request: Request, body: KillSwitchRequest):
    """
    POST /api/admin/kill-switch

    Immediately disables all signal generation. All simulation endpoints will
    return HTTP 503 until /api/admin/resume is called.

    Body: {"reason": "Data feed anomaly detected"}
    Requires: X-API-Key header
    """
    from server import require_api_key
    require_api_key(request)

    if not is_signals_enabled():
        return {
            "status": "already_paused",
            "message": "System was already paused",
            "state": get_system_state(),
        }

    activate_kill_switch(body.reason)
    logger.warning(
        "Kill switch activated by %s — reason: %s",
        request.client.host if request.client else "unknown",
        body.reason,
    )
    return {
        "status": "paused",
        "message": "Signal generation disabled",
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "reason": body.reason,
    }


@router.post("/api/admin/resume")
async def resume(request: Request, body: ResumeRequest):
    """
    POST /api/admin/resume

    Re-enables signal generation after a kill switch activation.

    Body: {"confirm": true}
    Requires: X-API-Key header
    """
    from server import require_api_key
    require_api_key(request)

    if not body.confirm:
        raise HTTPException(status_code=400, detail='confirm must be true to resume signals')

    if is_signals_enabled():
        return {
            "status": "already_active",
            "message": "System was already running",
            "state": get_system_state(),
        }

    resume_signals()
    logger.info(
        "Signals resumed by %s",
        request.client.host if request.client else "unknown",
    )
    return {
        "status": "resumed",
        "message": "Signal generation re-enabled",
        "resumed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/admin/status")
async def system_status():
    """
    GET /api/admin/status

    Returns current system state including kill switch status, paper mode,
    and environment. No authentication required (safe for monitoring dashboards).
    """
    state = get_system_state()

    # Add basic prediction stats if available
    try:
        from database import get_detailed_accuracy_stats
        stats = await get_detailed_accuracy_stats(ticker=None)
        state["prediction_stats"] = {
            "total_predictions": stats.get("total_predictions", 0),
            "resolved": stats.get("resolved_predictions", 0),
            "direction_accuracy_pct": stats.get("direction_accuracy_pct"),
        }
    except Exception:
        state["prediction_stats"] = None

    state["timestamp"] = datetime.now(timezone.utc).isoformat()
    return state


@router.get("/api/health/data-feeds")
async def data_feed_health():
    """
    GET /api/health/data-feeds

    Live health check of all data sources used by the simulation pipeline.
    Reports per-feed status, response times, and whether signals are currently
    being blocked due to data unavailability.

    No authentication required.
    """
    from monitoring.data_health import check_feeds
    report = await check_feeds(timeout=12.0)
    return report


@router.post("/api/admin/validate-predictions")
async def trigger_validation(request: Request):
    """
    POST /api/admin/validate-predictions

    Manually trigger the 24-hour outcome validation job. Validates all
    prediction_log entries that are older than 24h and not yet resolved.

    Returns a summary of how many were validated and the resulting hit rate.
    Requires: X-API-Key header
    """
    from server import require_api_key
    require_api_key(request)

    from validation.outcome_checker import run_validation_job
    result = await run_validation_job()
    result["triggered_at"] = datetime.now(timezone.utc).isoformat()
    return result


@router.get("/api/metrics/validation-summary")
async def validation_summary(days: int = 30):
    """
    GET /api/metrics/validation-summary?days=30

    Accuracy breakdown for predictions resolved in the last N days.
    Includes overall hit rate, breakdown by direction (BUY/SELL), and
    breakdown by confidence band (55-65%, 65-75%, 75-85%, 85%+).

    No authentication required.
    """
    if days < 1 or days > 365:
        raise HTTPException(status_code=400, detail="days must be between 1 and 365")

    from validation.outcome_checker import get_validation_summary
    return await get_validation_summary(days=days)
