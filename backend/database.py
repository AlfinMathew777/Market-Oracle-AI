"""SQLite persistence layer for Market Oracle AI.

Tables:
  simulations    — existing prediction history (backward compatible)
  events         — de-duplicated ACLED events
  prediction_log — Upgrade 5: full prediction log with reflection fields

DB path: /data/aussieintel.db on Render/Railway (persistent disk),
         ./aussieintel.db in local dev.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

_DB_DIR = os.environ.get("DATA_DIR", "/data" if os.path.isdir("/data") else ".")
DB_PATH = os.path.join(_DB_DIR, "aussieintel.db")

_init_lock   = asyncio.Lock()
_initialized = False


def get_db():
    """Return an aiosqlite connection context manager. Use as: async with get_db() as db:"""
    import aiosqlite
    return aiosqlite.connect(DB_PATH)


async def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    global _initialized
    async with _init_lock:
        if _initialized:
            return
        import aiosqlite
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
                -- ── Existing table: simulations ──────────────────────────────
                CREATE TABLE IF NOT EXISTS simulations (
                    id               TEXT PRIMARY KEY,
                    ticker           TEXT NOT NULL,
                    direction        TEXT NOT NULL,
                    confidence       REAL,
                    event_description TEXT,
                    event_type       TEXT,
                    country          TEXT,
                    causal_chain     TEXT,
                    agent_votes      TEXT,
                    execution_time   REAL,
                    ticker_confidence REAL,
                    ticker_reasoning TEXT,
                    outcome          TEXT,
                    check_at         INTEGER,
                    actual_change_pct REAL,
                    created_at       TEXT NOT NULL
                );

                -- ── Existing table: events ────────────────────────────────────
                CREATE TABLE IF NOT EXISTS events (
                    id             TEXT PRIMARY KEY,
                    acled_event_id TEXT,
                    country        TEXT,
                    event_type     TEXT,
                    lat            REAL,
                    lon            REAL,
                    fatalities     INTEGER DEFAULT 0,
                    created_at     TEXT NOT NULL
                );

                -- ── UPGRADE 5: prediction_log ─────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS prediction_log (
                    id                      TEXT PRIMARY KEY,
                    ticker                  TEXT NOT NULL,
                    predicted_direction     TEXT NOT NULL,
                    confidence              REAL,
                    predicted_at            TEXT NOT NULL,
                    primary_reason          TEXT,

                    -- Market snapshot at prediction time
                    iron_ore_at_prediction  REAL,
                    audusd_at_prediction    REAL,
                    brent_at_prediction     REAL,
                    bhp_price_at_prediction REAL,

                    -- Agent vote counts
                    agent_bullish           INTEGER,
                    agent_bearish           INTEGER,
                    agent_neutral           INTEGER,

                    -- Trend context
                    trend_label             TEXT,

                    -- Filled in by run_reflection.py after market close
                    actual_direction        TEXT,
                    actual_close_price      REAL,
                    actual_price_change_pct REAL,
                    prediction_correct      INTEGER,   -- 0/1 boolean
                    actual_driver           TEXT,
                    reason_matched          INTEGER,   -- 0/1 boolean
                    lesson                  TEXT,
                    resolved_at             TEXT,
                    resolution_notes        TEXT,

                    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
                );

                -- ── Indexes ───────────────────────────────────────────────────
                CREATE INDEX IF NOT EXISTS idx_sim_ticker   ON simulations(ticker);
                CREATE INDEX IF NOT EXISTS idx_sim_created  ON simulations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sim_check_at ON simulations(check_at);

                CREATE INDEX IF NOT EXISTS idx_log_ticker   ON prediction_log(ticker);
                CREATE INDEX IF NOT EXISTS idx_log_predicted_at ON prediction_log(predicted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_log_unresolved ON prediction_log(actual_direction)
                    WHERE actual_direction IS NULL;
            """)
            await db.commit()

        # ── Migrate existing prediction_log tables (add new columns if missing) ──
        new_cols = [
            ("agent_bullish",        "INTEGER"),
            ("agent_bearish",        "INTEGER"),
            ("agent_neutral",        "INTEGER"),
            ("trend_label",          "TEXT"),
            ("actual_close_price",   "REAL"),
            ("resolved_at",          "TEXT"),
            ("resolution_notes",     "TEXT"),
        ]
        async with aiosqlite.connect(DB_PATH) as db:
            for col, col_type in new_cols:
                try:
                    await db.execute(f"ALTER TABLE prediction_log ADD COLUMN {col} {col_type}")
                    await db.commit()
                    logger.info("Migrated prediction_log: added column %s", col)
                except Exception:
                    pass  # Column already exists

        _initialized = True
        logger.info("Database initialised at %s", DB_PATH)


# ── simulations table ──────────────────────────────────────────────────────────

async def save_simulation(
    simulation_id: str,
    ticker: str,
    prediction,
    event_data: dict,
    execution_time: float,
) -> None:
    """Persist completed simulation result. Non-blocking (called via create_task)."""
    try:
        await init_db()
        import json, time

        p        = prediction if isinstance(prediction, dict) else prediction.model_dump()
        check_at = int(time.time()) + 86400

        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO simulations
                   (id, ticker, direction, confidence, event_description, event_type,
                    country, causal_chain, agent_votes, execution_time,
                    ticker_confidence, ticker_reasoning, outcome, check_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    simulation_id, ticker,
                    p.get("direction", "NEUTRAL"),
                    p.get("confidence", 0.0),
                    event_data.get("notes") or event_data.get("location", ""),
                    event_data.get("event_type", ""),
                    event_data.get("country", ""),
                    json.dumps(p.get("causal_chain", [])),
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
        logger.info("Saved simulation %s to simulations table", simulation_id)
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

        query  = "SELECT * FROM simulations"
        params: list = []
        if ticker:
            query += " WHERE ticker = ?"
            params.append(ticker)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with get_db() as db:
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
    """Return prediction accuracy percentages from simulations table."""
    try:
        await init_db()
        where  = "WHERE outcome != 'PENDING'" + (" AND ticker = ?" if ticker else "")
        params = [ticker] if ticker else []

        async with get_db() as db:
            async with db.execute(
                f"SELECT outcome, COUNT(*) as n FROM simulations {where} GROUP BY outcome",
                params,
            ) as cur:
                rows = await cur.fetchall()

        counts  = {r[0]: r[1] for r in rows}
        total   = sum(counts.values())
        if total == 0:
            return {"total": 0, "accuracy_pct": None, "breakdown": counts}

        correct = counts.get("CORRECT", 0)
        return {
            "total":       total,
            "correct":     correct,
            "accuracy_pct": round(correct / total * 100, 1),
            "breakdown":   counts,
        }
    except Exception as e:
        logger.error("get_accuracy_stats failed: %s", e)
        return {"total": 0, "accuracy_pct": None, "error": str(e)}


async def run_accuracy_checks() -> int:
    """Check simulations past their 24h mark and update PENDING outcomes."""
    try:
        await init_db()
        import time

        now = int(time.time())
        async with get_db() as db:
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
                info    = yf.Ticker(ticker).fast_info
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

                    async with get_db() as db:
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


# ── prediction_log table ───────────────────────────────────────────────────────

async def get_unresolved_predictions(ticker: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Return predictions where actual_direction IS NULL (not yet reflected)."""
    try:
        await init_db()
        query  = "SELECT * FROM prediction_log WHERE actual_direction IS NULL"
        params: list = []
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        query += " ORDER BY predicted_at DESC LIMIT ?"
        params.append(limit)

        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(query, params) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error("get_unresolved_predictions failed: %s", e)
        return []


async def update_prediction_reflection(
    prediction_id: str,
    actual_direction: str,
    actual_price_change_pct: float,
    prediction_correct: bool,
    actual_driver: str,
    reason_matched: bool,
    lesson: str,
) -> None:
    """Write reflection results back to prediction_log."""
    try:
        await init_db()
        async with get_db() as db:
            await db.execute(
                """UPDATE prediction_log SET
                   actual_direction=?, actual_price_change_pct=?,
                   prediction_correct=?, actual_driver=?,
                   reason_matched=?, lesson=?
                   WHERE id=?""",
                (
                    actual_direction,
                    round(actual_price_change_pct, 4),
                    int(prediction_correct),
                    actual_driver[:500] if actual_driver else "",
                    int(reason_matched),
                    lesson[:1000] if lesson else "",
                    prediction_id,
                ),
            )
            await db.commit()
        logger.info("Reflection saved for %s", prediction_id)
    except Exception as e:
        logger.error("update_prediction_reflection failed for %s: %s", prediction_id, e)


async def get_prediction_log_accuracy(ticker: Optional[str] = None) -> Optional[float]:
    """Return rolling accuracy from prediction_log as a 0-1 float."""
    try:
        await init_db()
        where  = "WHERE prediction_correct IS NOT NULL" + (" AND ticker=?" if ticker else "")
        params = [ticker] if ticker else []
        async with get_db() as db:
            async with db.execute(
                f"SELECT AVG(prediction_correct) FROM prediction_log {where}", params
            ) as cur:
                row = await cur.fetchone()
        return round(float(row[0]), 3) if row and row[0] is not None else None
    except Exception as e:
        logger.warning("get_prediction_log_accuracy failed: %s", e)
        return None


async def save_prediction_log(
    simulation_id: str,
    ticker: str,
    direction: str,       # "UP" | "DOWN" | "NEUTRAL"
    confidence: float,
    primary_reason: str,
    market_ctx: dict,
    agent_bullish: int = 0,
    agent_bearish: int = 0,
    agent_neutral: int = 0,
    trend_label: Optional[str] = None,
) -> None:
    """Save a full prediction to prediction_log. Called non-blocking after every simulation."""
    try:
        await init_db()
        # Normalize direction to lowercase for consistency with reflection script
        pred_dir = {"UP": "bullish", "DOWN": "bearish", "NEUTRAL": "neutral"}.get(
            direction.upper(), direction.lower()
        )
        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO prediction_log
                   (id, ticker, predicted_direction, confidence, predicted_at,
                    primary_reason,
                    iron_ore_at_prediction, audusd_at_prediction,
                    brent_at_prediction, bhp_price_at_prediction,
                    agent_bullish, agent_bearish, agent_neutral, trend_label)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    simulation_id, ticker, pred_dir, confidence,
                    datetime.now(timezone.utc).isoformat(),
                    primary_reason[:500] if primary_reason else "",
                    market_ctx.get("iron_ore_price"),
                    market_ctx.get("audusd_rate"),
                    market_ctx.get("brent_price"),
                    market_ctx.get("ticker_price"),
                    agent_bullish, agent_bearish, agent_neutral,
                    trend_label,
                )
            )
            await db.commit()
        logger.info("Saved prediction_log entry: %s (%s %s %.0f%%)",
                    simulation_id, ticker, pred_dir, confidence * 100)
    except Exception as e:
        logger.error("save_prediction_log failed for %s: %s", simulation_id, e)


async def get_full_prediction_log(
    ticker: Optional[str] = None,
    days: int = 30,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return prediction log entries with optional ticker filter and day window."""
    try:
        await init_db()
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        conditions = ["predicted_at >= ?"]
        params: list = [since]
        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)

        where = " AND ".join(conditions)
        params.append(limit)

        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                f"SELECT * FROM prediction_log WHERE {where} ORDER BY predicted_at DESC LIMIT ?",
                params,
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error("get_full_prediction_log failed: %s", e)
        return []


async def get_detailed_accuracy_stats(ticker: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns comprehensive accuracy stats including:
    - Overall accuracy
    - Breakdown by direction (bullish/bearish/neutral)
    - Breakdown by confidence band (0-25%, 25-50%, 50-75%, 75-100%)
    - Current streak and best streak
    """
    try:
        await init_db()
        base_where = "WHERE prediction_correct IS NOT NULL"
        params: list = []
        if ticker:
            base_where += " AND ticker = ?"
            params.append(ticker)

        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

            # Total predictions (including unresolved)
            total_where = "WHERE 1=1" + (" AND ticker=?" if ticker else "")
            total_params = [ticker] if ticker else []
            async with db.execute(
                f"SELECT COUNT(*) as n FROM prediction_log {total_where}", total_params
            ) as cur:
                total_row = await cur.fetchone()
            total_predictions = total_row["n"] if total_row else 0

            # Resolved predictions
            async with db.execute(
                f"SELECT COUNT(*) as n, SUM(prediction_correct) as correct, AVG(confidence) as avg_conf "
                f"FROM prediction_log {base_where}",
                params,
            ) as cur:
                overall = await cur.fetchone()

            resolved = overall["n"] if overall else 0
            correct  = int(overall["correct"] or 0) if overall else 0
            avg_conf = float(overall["avg_conf"] or 0) if overall else 0

            # By direction
            async with db.execute(
                f"SELECT predicted_direction, COUNT(*) as total, SUM(prediction_correct) as correct "
                f"FROM prediction_log {base_where} GROUP BY predicted_direction",
                params,
            ) as cur:
                dir_rows = await cur.fetchall()

            accuracy_by_direction: Dict[str, Any] = {}
            for row in dir_rows:
                d = row["predicted_direction"]
                t = row["total"]
                c = int(row["correct"] or 0)
                accuracy_by_direction[d] = {
                    "total": t,
                    "correct": c,
                    "accuracy_pct": round(c / t * 100, 1) if t > 0 else 0,
                }

            # By confidence band
            bands = [
                ("0-25%",   0,    0.25),
                ("25-50%",  0.25, 0.50),
                ("50-75%",  0.50, 0.75),
                ("75-100%", 0.75, 1.01),
            ]
            accuracy_by_confidence_band: Dict[str, Any] = {}
            for label, lo, hi in bands:
                band_params = list(params) + [lo, hi]
                async with db.execute(
                    f"SELECT COUNT(*) as total, SUM(prediction_correct) as correct "
                    f"FROM prediction_log {base_where} AND confidence >= ? AND confidence < ?",
                    band_params,
                ) as cur:
                    band_row = await cur.fetchone()
                t = band_row["total"] if band_row else 0
                c = int(band_row["correct"] or 0) if band_row else 0
                accuracy_by_confidence_band[label] = {
                    "total": t,
                    "correct": c,
                    "accuracy_pct": round(c / t * 100, 1) if t > 0 else 0,
                }

            # Streak calculation — ordered by predicted_at DESC
            streak_params = list(params)
            async with db.execute(
                f"SELECT prediction_correct FROM prediction_log {base_where} ORDER BY predicted_at DESC",
                streak_params,
            ) as cur:
                streak_rows = await cur.fetchall()

        # Calculate streaks
        current_streak = 0
        streak_direction = "correct"
        best_streak = 0
        running = 0
        last_val = None
        for row in streak_rows:
            val = row["prediction_correct"]
            if last_val is None:
                last_val = val
                running = 1
                current_streak = 1
                streak_direction = "correct" if val else "wrong"
            elif val == last_val:
                running += 1
                if running > best_streak:
                    best_streak = running
            else:
                running = 1
                last_val = val

        if streak_rows:
            # current_streak = consecutive from the start of the result set
            first_val = streak_rows[0]["prediction_correct"]
            streak_direction = "correct" if first_val else "wrong"
            current_streak = 0
            for row in streak_rows:
                if row["prediction_correct"] == first_val:
                    current_streak += 1
                else:
                    break

        # Best streak
        best = 0
        run = 0
        prev = None
        for row in streak_rows:
            v = row["prediction_correct"]
            if v == prev:
                run += 1
            else:
                run = 1
                prev = v
            if run > best:
                best = run
        best_streak = best

        return {
            "total_predictions":    total_predictions,
            "resolved_predictions": resolved,
            "correct_predictions":  correct,
            "direction_accuracy_pct": round(correct / resolved * 100, 1) if resolved > 0 else 0,
            "avg_confidence":       round(avg_conf * 100, 1),
            "accuracy_by_direction": accuracy_by_direction,
            "accuracy_by_confidence_band": accuracy_by_confidence_band,
            "streak": {
                "current_streak":    current_streak,
                "streak_direction":  streak_direction,
                "best_streak":       best_streak,
            },
        }
    except Exception as e:
        logger.error("get_detailed_accuracy_stats failed: %s", e)
        return {
            "total_predictions": 0, "resolved_predictions": 0,
            "correct_predictions": 0, "direction_accuracy_pct": 0,
            "avg_confidence": 0,
            "accuracy_by_direction": {}, "accuracy_by_confidence_band": {},
            "streak": {"current_streak": 0, "streak_direction": "correct", "best_streak": 0},
        }


async def update_prediction_resolution(
    prediction_id: str,
    actual_direction: str,
    actual_close_price: float,
    actual_price_change_pct: float,
    prediction_correct: bool,
    actual_driver: str,
    reason_matched: bool,
    lesson: str,
    resolved_at: str,
    resolution_notes: str = "",
) -> None:
    """Full resolution update — replaces update_prediction_reflection with richer fields."""
    try:
        await init_db()
        async with get_db() as db:
            await db.execute(
                """UPDATE prediction_log SET
                   actual_direction=?, actual_close_price=?, actual_price_change_pct=?,
                   prediction_correct=?, actual_driver=?,
                   reason_matched=?, lesson=?,
                   resolved_at=?, resolution_notes=?
                   WHERE id=?""",
                (
                    actual_direction,
                    actual_close_price,
                    round(actual_price_change_pct, 4),
                    int(prediction_correct),
                    actual_driver[:500] if actual_driver else "",
                    int(reason_matched),
                    lesson[:1000] if lesson else "",
                    resolved_at,
                    resolution_notes[:500] if resolution_notes else "",
                    prediction_id,
                ),
            )
            await db.commit()
        logger.info("Resolution saved for %s: %s (correct=%s)", prediction_id, actual_direction, prediction_correct)
    except Exception as e:
        logger.error("update_prediction_resolution failed for %s: %s", prediction_id, e)
