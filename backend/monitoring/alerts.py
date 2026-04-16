"""
Alert system for Market Oracle AI.

Five alert types, each with its own trigger condition, severity, and cooldown:

  ACCURACY_DROP          — 7-day hit rate < 50%            critical   60 min cooldown
  DATA_FEED_STALE        — critical feed silent > 30 min   critical   30 min cooldown
  HIGH_SIGNAL_VOLUME     — > 10 signals in last hour        warning    60 min cooldown
  LOW_CONFIDENCE_CLUSTER — 5 consecutive signals < 60%     warning   120 min cooldown
  MONTE_CARLO_INSTABILITY— avg MC stability < 35% (10 sig) warning    60 min cooldown

Alerts are written to the `alerts` SQLite table and logged to the console.
Email / Slack delivery can be added by hooking into `_notify()`.

Deduplication: a new alert is suppressed if an identical (same type + same
context key, unacknowledged) alert already exists within the cooldown window.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Alert type constants ───────────────────────────────────────────────────────

ACCURACY_DROP           = "ACCURACY_DROP"
DATA_FEED_STALE         = "DATA_FEED_STALE"
HIGH_SIGNAL_VOLUME      = "HIGH_SIGNAL_VOLUME"
LOW_CONFIDENCE_CLUSTER  = "LOW_CONFIDENCE_CLUSTER"
MONTE_CARLO_INSTABILITY = "MONTE_CARLO_INSTABILITY"
ML_ANOMALY              = "ML_ANOMALY"

# Cooldown minutes per alert type — a new alert won't fire if an identical
# unacknowledged one already exists within this window.
_COOLDOWNS: dict[str, int] = {
    ACCURACY_DROP:           60,
    DATA_FEED_STALE:         30,
    HIGH_SIGNAL_VOLUME:      60,
    LOW_CONFIDENCE_CLUSTER:  120,
    MONTE_CARLO_INSTABILITY: 60,
    ML_ANOMALY:              120,   # re-check every 2h to avoid alert fatigue
}


# ── Low-level DB helpers ───────────────────────────────────────────────────────

async def _is_duplicate(
    alert_type: str,
    dedup_key: str,
    cooldown_minutes: int,
) -> bool:
    """
    Return True if an unacknowledged alert of the same type with the same
    dedup_key already exists within the cooldown window.

    dedup_key is a short string extracted from the alert context (e.g. feed name
    for DATA_FEED_STALE, empty string for alerts with no sub-key).
    """
    from database import get_db, init_db
    await init_db()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    ).isoformat()
    try:
        async with get_db() as db:
            async with db.execute(
                """SELECT COUNT(*) FROM alerts
                   WHERE alert_type = ?
                     AND acknowledged_at IS NULL
                     AND created_at >= ?
                     AND (? = '' OR context LIKE ?)""",
                (alert_type, cutoff, dedup_key, f"%{dedup_key}%"),
            ) as cur:
                row = await cur.fetchone()
        return (row[0] if row else 0) > 0
    except Exception as e:
        logger.warning("_is_duplicate check failed (non-fatal): %s", e)
        return False  # Fail open — better to fire a duplicate than miss one


async def _insert_alert(
    alert_type: str,
    severity: str,
    message: str,
    context: Optional[dict] = None,
) -> Optional[int]:
    """
    Insert a new alert row. Returns the new row id, or None on failure.
    """
    from database import get_db, init_db
    await init_db()
    ctx_json = json.dumps(context) if context else None
    try:
        async with get_db() as db:
            cur = await db.execute(
                """INSERT INTO alerts (alert_type, severity, message, context, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    alert_type,
                    severity,
                    message,
                    ctx_json,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("_insert_alert failed for %s: %s", alert_type, e)
        return None


def _notify(alert_type: str, severity: str, message: str) -> None:
    """
    Console notification. Extend this to send email/Slack when ready.
    Log level matches severity so critical alerts appear as ERROR in Railway logs.
    """
    log = logger.error if severity == "critical" else logger.warning
    log("[ALERT:%s] %s: %s", severity, alert_type, message)


async def _fire_alert(
    alert_type: str,
    severity: str,
    message: str,
    context: Optional[dict] = None,
    dedup_key: str = "",
) -> Optional[dict]:
    """
    Fire an alert: deduplicate, persist, and notify.
    Returns the alert dict if it was created, or None if suppressed.
    """
    cooldown = _COOLDOWNS.get(alert_type, 60)
    if await _is_duplicate(alert_type, dedup_key, cooldown):
        logger.debug("Alert suppressed (duplicate within %d min): %s", cooldown, alert_type)
        return None

    row_id = await _insert_alert(alert_type, severity, message, context)
    if row_id is None:
        return None

    _notify(alert_type, severity, message)

    return {
        "id": row_id,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "context": context,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Individual alert checks ────────────────────────────────────────────────────

async def check_accuracy_drop() -> Optional[dict]:
    """
    ACCURACY_DROP — fires when 7-day hit rate falls below 50%.
    Uses the existing prediction_log accuracy stats.
    """
    try:
        from database import get_detailed_accuracy_stats
        stats = await get_detailed_accuracy_stats(ticker=None, days=7)
        resolved = stats.get("resolved_predictions", 0) or 0
        if resolved < 5:
            return None  # Not enough data to judge
        accuracy_pct = stats.get("direction_accuracy_pct", 50) or 50
        if accuracy_pct >= 50:
            return None

        correct = stats.get("correct_predictions", 0) or 0
        ctx = {"hit_rate_pct": accuracy_pct, "correct": correct, "total": resolved, "days": 7}
        message = f"7-day accuracy dropped to {accuracy_pct:.0f}% ({correct}/{resolved})"
        return await _fire_alert(ACCURACY_DROP, "critical", message, ctx)
    except Exception as e:
        logger.warning("check_accuracy_drop failed (non-fatal): %s", e)
        return None


async def check_data_feed_stale() -> list[dict]:
    """
    DATA_FEED_STALE — fires for each critical feed that hasn't been fetched
    for > 30 minutes.  Only checks feeds that have been seen at least once
    (avoids false alerts on cold start).
    """
    import time
    from monitoring.data_health import _last_success

    STALE_MINUTES = 30
    CRITICAL_FEEDS = {"asx_prices"}   # Only block-worthy feeds trigger this alert
    new_alerts: list[dict] = []

    now = time.time()
    for feed_name, last_ts in list(_last_success.items()):
        if feed_name not in CRITICAL_FEEDS:
            continue
        age_minutes = (now - last_ts) / 60
        if age_minutes < STALE_MINUTES:
            continue

        ctx = {"feed": feed_name, "age_minutes": round(age_minutes, 1)}
        message = f"{feed_name} stale for {age_minutes:.0f} minutes"
        alert = await _fire_alert(
            DATA_FEED_STALE, "critical", message, ctx, dedup_key=feed_name
        )
        if alert:
            new_alerts.append(alert)

    return new_alerts


async def check_high_signal_volume() -> Optional[dict]:
    """
    HIGH_SIGNAL_VOLUME — fires when > 10 signals are generated in the last hour.
    """
    THRESHOLD = 10
    try:
        from database import get_db, init_db
        await init_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        async with get_db() as db:
            async with db.execute(
                """SELECT COUNT(*) FROM prediction_log
                   WHERE predicted_at >= ?
                     AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)""",
                (cutoff,),
            ) as cur:
                row = await cur.fetchone()
        count = row[0] if row else 0
        if count <= THRESHOLD:
            return None

        ctx = {"count": count, "window_minutes": 60, "threshold": THRESHOLD}
        message = f"{count} signals in last hour (threshold: {THRESHOLD})"
        return await _fire_alert(HIGH_SIGNAL_VOLUME, "warning", message, ctx)
    except Exception as e:
        logger.warning("check_high_signal_volume failed (non-fatal): %s", e)
        return None


async def check_low_confidence_cluster() -> Optional[dict]:
    """
    LOW_CONFIDENCE_CLUSTER — fires when the last 5 consecutive quality signals
    all have confidence below 60%.
    """
    WINDOW = 5
    THRESHOLD = 0.60
    try:
        from database import get_db, init_db
        await init_db()
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT confidence FROM prediction_log
                   WHERE (excluded_from_stats IS NULL OR excluded_from_stats = 0)
                     AND predicted_direction NOT IN ('neutral')
                   ORDER BY predicted_at DESC
                   LIMIT ?""",
                (WINDOW,),
            ) as cur:
                rows = await cur.fetchall()

        if len(rows) < WINDOW:
            return None

        confidences = [r["confidence"] or 0.0 for r in rows]
        if any(c >= THRESHOLD for c in confidences):
            return None  # At least one was high-confidence — not a cluster

        max_conf = max(confidences)
        ctx = {
            "consecutive": WINDOW,
            "threshold_pct": int(THRESHOLD * 100),
            "max_confidence_pct": round(max_conf * 100, 1),
        }
        message = (
            f"{WINDOW} consecutive low-confidence signals "
            f"(all below {int(THRESHOLD * 100)}%, max was {max_conf*100:.0f}%)"
        )
        return await _fire_alert(LOW_CONFIDENCE_CLUSTER, "warning", message, ctx)
    except Exception as e:
        logger.warning("check_low_confidence_cluster failed (non-fatal): %s", e)
        return None


async def check_ml_anomaly_alert() -> Optional[dict]:
    """
    ML_ANOMALY — fires when the IsolationForest detects an unusual signal pattern.

    Pulls from monitoring.anomaly_detector.check_ml_anomaly() which trains and
    predicts in a single call, re-training every 6 hours automatically.
    """
    try:
        from monitoring.anomaly_detector import check_ml_anomaly
        result = await check_ml_anomaly()
        if result is None or not result.get("anomaly"):
            return None

        score = result.get("score", 0)
        reason = result.get("reason", "ML anomaly detected")
        features = result.get("features", {})

        ctx = {
            "score": score,
            "reason": reason,
            "features": features,
            "trained_at": result.get("trained_at"),
        }
        message = f"{reason} (isolation score {score:.3f})"
        return await _fire_alert(ML_ANOMALY, "warning", message, ctx)
    except Exception as e:
        logger.warning("check_ml_anomaly_alert failed (non-fatal): %s", e)
        return None


async def check_monte_carlo_instability() -> Optional[dict]:
    """
    MONTE_CARLO_INSTABILITY — fires when the average MC price_stability_score
    across the last 10 simulations is below 35%.

    Extracts stability from full_json in the simulations table.
    Gracefully skips if stability data is absent (field not yet populated).
    """
    SAMPLES = 10
    THRESHOLD = 0.35
    try:
        from database import get_db, init_db
        await init_db()
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT full_json FROM simulations
                   WHERE full_json IS NOT NULL
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (SAMPLES,),
            ) as cur:
                rows = await cur.fetchall()

        stability_scores: list[float] = []
        for row in rows:
            try:
                pred = json.loads(row["full_json"])
                mc = pred.get("monte_carlo_price") or {}
                # Try common field names from quant engine
                score = (
                    mc.get("price_stability_score")
                    or mc.get("stability_score")
                    or mc.get("stability")
                )
                if score is not None:
                    stability_scores.append(float(score))
            except Exception:
                continue

        if len(stability_scores) < 3:
            return None  # Not enough MC data to trigger this alert

        avg_stability = sum(stability_scores) / len(stability_scores)
        if avg_stability >= THRESHOLD:
            return None

        ctx = {
            "avg_stability_pct": round(avg_stability * 100, 1),
            "threshold_pct": int(THRESHOLD * 100),
            "samples": len(stability_scores),
        }
        message = (
            f"Monte Carlo stability averaging {avg_stability*100:.0f}% "
            f"(threshold: {int(THRESHOLD * 100)}%) over last {len(stability_scores)} signals"
        )
        return await _fire_alert(MONTE_CARLO_INSTABILITY, "warning", message, ctx)
    except Exception as e:
        logger.warning("check_monte_carlo_instability failed (non-fatal): %s", e)
        return None


# ── Orchestrator ───────────────────────────────────────────────────────────────

async def check_all_alerts() -> list[dict]:
    """
    Run all alert checks concurrently. Returns a list of newly created alerts.
    Safe to call frequently — each check is idempotent and deduplicates itself.
    """
    results = await asyncio.gather(
        check_accuracy_drop(),
        check_data_feed_stale(),
        check_high_signal_volume(),
        check_low_confidence_cluster(),
        check_monte_carlo_instability(),
        return_exceptions=True,
    )

    new_alerts: list[dict] = []
    for result in results:
        if isinstance(result, Exception):
            logger.error("Alert check raised exception (non-fatal): %s", result)
        elif isinstance(result, list):
            new_alerts.extend(a for a in result if a)
        elif result is not None:
            new_alerts.append(result)

    if new_alerts:
        logger.info("check_all_alerts: %d new alert(s) created", len(new_alerts))
    return new_alerts


# ── CRUD ───────────────────────────────────────────────────────────────────────

async def get_active_alerts() -> list[dict]:
    """Return unacknowledged alerts, newest first."""
    from database import get_db, init_db
    await init_db()
    try:
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT id, alert_type, severity, message, context, created_at
                   FROM alerts
                   WHERE acknowledged_at IS NULL
                   ORDER BY created_at DESC""",
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            if row.get("context"):
                try:
                    row["context"] = json.loads(row["context"])
                except Exception:
                    pass
        return rows
    except Exception as e:
        logger.error("get_active_alerts failed: %s", e)
        return []


async def get_alert_history(limit: int = 50) -> list[dict]:
    """Return all alerts (acknowledged and unacknowledged), newest first."""
    from database import get_db, init_db
    await init_db()
    try:
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT id, alert_type, severity, message, context,
                          created_at, acknowledged_at, acknowledged_by
                   FROM alerts
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            if row.get("context"):
                try:
                    row["context"] = json.loads(row["context"])
                except Exception:
                    pass
        return rows
    except Exception as e:
        logger.error("get_alert_history failed: %s", e)
        return []


async def acknowledge_alert(alert_id: int, by: str) -> bool:
    """
    Mark an alert as acknowledged. Returns True on success, False if not found.
    """
    from database import get_db, init_db
    await init_db()
    try:
        async with get_db() as db:
            result = await db.execute(
                """UPDATE alerts
                   SET acknowledged_at = ?,
                       acknowledged_by = ?
                   WHERE id = ?
                     AND acknowledged_at IS NULL""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    by[:100] if by else "unknown",
                    alert_id,
                ),
            )
            await db.commit()
            updated = result.rowcount > 0
        if updated:
            logger.info("Alert %d acknowledged by %s", alert_id, by)
        else:
            logger.warning("Alert %d not found or already acknowledged", alert_id)
        return updated
    except Exception as e:
        logger.error("acknowledge_alert failed for id=%d: %s", alert_id, e)
        return False
