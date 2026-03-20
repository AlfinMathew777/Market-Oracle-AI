"""SQLite persistence layer for AussieIntel.

Tables:
  simulations — prediction history (survives restarts via Render persistent disk)
  events      — de-duplicated ACLED events seen by the platform

Database path: /data/aussieintel.db on Render (persistent disk),
               ./aussieintel.db in local dev.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Persistent disk on Render mounts at /data; fall back to cwd for local dev
_DB_DIR  = os.environ.get("DATA_DIR", "/data" if os.path.isdir("/data") else ".")
DB_PATH  = os.path.join(_DB_DIR, "aussieintel.db")

_init_lock = asyncio.Lock()
_initialized = False


async def get_db():
    """Return an aiosqlite connection (caller must close it)."""
    import aiosqlite
    return await aiosqlite.connect(DB_PATH)


async def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    global _initialized
    async with _init_lock:
        if _initialized:
            return
        import aiosqlite
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS simulations (
                    id               TEXT PRIMARY KEY,
                    ticker           TEXT NOT NULL,
                    direction        TEXT NOT NULL,   -- UP / DOWN / NEUTRAL
                    confidence       REAL,
                    event_description TEXT,
                    event_type       TEXT,
                    country          TEXT,
                    causal_chain     TEXT,
                    agent_votes      TEXT,            -- JSON string
                    execution_time   REAL,
                    ticker_confidence REAL,
                    ticker_reasoning TEXT,
                    outcome          TEXT,            -- CORRECT / INCORRECT / NEUTRAL / PENDING
                    check_at         INTEGER,         -- unix timestamp for 24h accuracy check
                    actual_change_pct REAL,
                    created_at       TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id               TEXT PRIMARY KEY,
                    acled_event_id   TEXT,
                    country          TEXT,
                    event_type       TEXT,
                    lat              REAL,
                    lon              REAL,
                    fatalities       INTEGER DEFAULT 0,
                    created_at       TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_sim_ticker    ON simulations(ticker);
                CREATE INDEX IF NOT EXISTS idx_sim_created   ON simulations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sim_check_at  ON simulations(check_at);
            """)
            await db.commit()
        _initialized = True
        logger.info("Database initialised at %s", DB_PATH)


async def save_simulation(
    simulation_id: str,
    ticker: str,
    prediction,          # PredictionCard pydantic model or dict
    event_data: dict,
    execution_time: float,
) -> None:
    """Persist a completed simulation result. Non-blocking (called via create_task)."""
    try:
        await init_db()
        import json, time
        from datetime import timedelta

        p = prediction if isinstance(prediction, dict) else prediction.dict()
        check_at = int(time.time()) + 86400  # 24 hours from now

        async with await get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO simulations
                   (id, ticker, direction, confidence, event_description, event_type,
                    country, causal_chain, agent_votes, execution_time,
                    ticker_confidence, ticker_reasoning, outcome, check_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    simulation_id,
                    ticker,
                    p.get("direction", "NEUTRAL"),
                    p.get("confidence", 0.0),
                    event_data.get("notes") or event_data.get("location", ""),
                    event_data.get("event_type", ""),
                    event_data.get("country", ""),
                    p.get("causal_chain", ""),
                    json.dumps(p.get("agent_votes", [])),
                    execution_time,
                    event_data.get("ticker_confidence", 0.5),
                    event_data.get("ticker_reasoning", ""),
                    "PENDING",
                    check_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
        logger.info("Saved simulation %s to DB", simulation_id)
    except Exception as e:
        logger.error("Failed to save simulation %s: %s", simulation_id, e)


async def get_prediction_history(
    ticker: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Return recent prediction history, optionally filtered by ticker."""
    try:
        await init_db()
        import json

        query = "SELECT * FROM simulations"
        params: list = []
        if ticker:
            query += " WHERE ticker = ?"
            params.append(ticker)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with await get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(query, params) as cur:
                rows = await cur.fetchall()

        for row in rows:
            if row.get("agent_votes"):
                try:
                    row["agent_votes"] = json.loads(row["agent_votes"])
                except Exception:
                    row["agent_votes"] = []
        return rows
    except Exception as e:
        logger.error("get_prediction_history failed: %s", e)
        return []


async def get_accuracy_stats(ticker: Optional[str] = None) -> Dict[str, Any]:
    """Return prediction accuracy percentages."""
    try:
        await init_db()
        where = "WHERE outcome != 'PENDING'" + (" AND ticker = ?" if ticker else "")
        params = [ticker] if ticker else []

        async with await get_db() as db:
            async with db.execute(
                f"SELECT outcome, COUNT(*) as n FROM simulations {where} GROUP BY outcome",
                params,
            ) as cur:
                rows = await cur.fetchall()

        counts = {r[0]: r[1] for r in rows}
        total  = sum(counts.values())
        if total == 0:
            return {"total": 0, "accuracy_pct": None, "breakdown": counts}

        correct = counts.get("CORRECT", 0)
        return {
            "total": total,
            "correct": correct,
            "accuracy_pct": round(correct / total * 100, 1),
            "breakdown": counts,
        }
    except Exception as e:
        logger.error("get_accuracy_stats failed: %s", e)
        return {"total": 0, "accuracy_pct": None, "error": str(e)}


async def run_accuracy_checks() -> int:
    """Check simulations past their 24h mark and update PENDING outcomes.

    Called by a cron job or background task every hour.
    Returns number of predictions checked.
    """
    try:
        await init_db()
        import time

        now = int(time.time())
        async with await get_db() as db:
            async with db.execute(
                "SELECT id, ticker, direction, created_at FROM simulations "
                "WHERE outcome = 'PENDING' AND check_at <= ?",
                (now,),
            ) as cur:
                pending = await cur.fetchall()

        if not pending:
            return 0

        import yfinance as yf
        checked = 0
        for sim_id, ticker, direction, created_at in pending:
            try:
                info = yf.Ticker(ticker).fast_info
                current = getattr(info, "last_price", None)
                prev    = getattr(info, "previous_close", current)
                if current and prev and prev > 0:
                    change_pct = (current - prev) / prev * 100
                    if abs(change_pct) < 0.5:
                        outcome = "NEUTRAL"
                    elif (direction == "UP" and change_pct > 0) or (direction == "DOWN" and change_pct < 0):
                        outcome = "CORRECT"
                    else:
                        outcome = "INCORRECT"

                    async with await get_db() as db:
                        await db.execute(
                            "UPDATE simulations SET outcome=?, actual_change_pct=? WHERE id=?",
                            (outcome, round(change_pct, 2), sim_id),
                        )
                        await db.commit()
                    checked += 1
            except Exception as e:
                logger.warning("Accuracy check failed for %s: %s", sim_id, e)

        logger.info("Accuracy check: updated %d/%d predictions", checked, len(pending))
        return checked
    except Exception as e:
        logger.error("run_accuracy_checks failed: %s", e)
        return 0
