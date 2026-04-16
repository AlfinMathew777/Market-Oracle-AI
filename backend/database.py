"""Persistence layer for Market Oracle AI.

Supports two backends:
  - SQLite  (default, local dev): when DATABASE_URL is not set
  - PostgreSQL (staging/prod):    when DATABASE_URL is set

Tables:
  simulations    — existing prediction history (backward compatible)
  events         — de-duplicated ACLED events
  prediction_log — Upgrade 5: full prediction log with reflection fields

DB path (SQLite): /data/aussieintel.db on Railway (persistent disk),
                  ./aussieintel.db in local dev.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ── Backend selection ─────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = bool(DATABASE_URL)

_DB_DIR = os.environ.get("DATA_DIR", "/data" if os.path.isdir("/data") else ".")
DB_PATH = os.path.join(_DB_DIR, "aussieintel.db")

_init_lock   = asyncio.Lock()
_initialized = False


def get_db():
    """
    Return an async context manager yielding a DB connection.

    - PostgreSQL: yields a PgConnection (db/connection.py)
    - SQLite:     yields an aiosqlite connection

    Use as: async with get_db() as db:
    """
    if _USE_POSTGRES:
        from db.connection import get_pg_db
        return get_pg_db()
    import aiosqlite
    return aiosqlite.connect(DB_PATH)


async def init_db() -> None:
    """Create all tables if they don't exist. Safe to call multiple times."""
    global _initialized
    async with _init_lock:
        if _initialized:
            return

        if _USE_POSTGRES:
            await _init_postgres()
            _initialized = True
            logger.info("PostgreSQL database initialised (DATABASE_URL set)")
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

                -- ── UPGRADE 6: reasoning_predictions ─────────────────────────
                -- Full predictions from the Reasoning Synthesizer with outcome tracking
                CREATE TABLE IF NOT EXISTS reasoning_predictions (
                    id                   TEXT PRIMARY KEY,
                    stock_ticker         TEXT NOT NULL,
                    prediction_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    direction            TEXT NOT NULL,
                    recommendation       TEXT NOT NULL,
                    confidence_score     INTEGER NOT NULL,
                    price_at_prediction  REAL NOT NULL,

                    -- Trade execution (if generated)
                    entry_price          REAL,
                    stop_loss            REAL,
                    take_profit_1        REAL,
                    take_profit_2        REAL,
                    take_profit_3        REAL,

                    -- Outcome tracking
                    outcome_status       TEXT NOT NULL DEFAULT 'PENDING',
                    outcome_timestamp    TEXT,
                    actual_return_pct    REAL,
                    hit_tp1              INTEGER DEFAULT 0,
                    hit_tp2              INTEGER DEFAULT 0,
                    hit_tp3              INTEGER DEFAULT 0,
                    hit_stop_loss        INTEGER DEFAULT 0,

                    -- Price checkpoints
                    price_1d             REAL,
                    price_7d             REAL,
                    price_30d            REAL,

                    -- Context (stored as JSON text)
                    event_classification TEXT,
                    causal_chain         TEXT,
                    market_context       TEXT,
                    agent_consensus      TEXT,
                    reasoning_output     TEXT NOT NULL,
                    trade_execution      TEXT,

                    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
                );

                -- ── Migration: add full_json column for restart recovery ─────
                -- ALTER TABLE is idempotent via the try/except in init_db().

                -- ── Indexes ───────────────────────────────────────────────────
                CREATE INDEX IF NOT EXISTS idx_sim_ticker   ON simulations(ticker);
                CREATE INDEX IF NOT EXISTS idx_sim_created  ON simulations(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sim_check_at ON simulations(check_at);

                CREATE INDEX IF NOT EXISTS idx_log_ticker   ON prediction_log(ticker);
                CREATE INDEX IF NOT EXISTS idx_log_predicted_at ON prediction_log(predicted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_log_unresolved ON prediction_log(actual_direction)
                    WHERE actual_direction IS NULL;

                CREATE INDEX IF NOT EXISTS idx_rp_ticker    ON reasoning_predictions(stock_ticker);
                CREATE INDEX IF NOT EXISTS idx_rp_timestamp ON reasoning_predictions(prediction_timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_rp_outcome   ON reasoning_predictions(outcome_status);
                CREATE INDEX IF NOT EXISTS idx_rp_direction ON reasoning_predictions(direction);

                -- ── UPGRADE 7: alerts ─────────────────────────────────────────
                CREATE TABLE IF NOT EXISTS alerts (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_type       TEXT NOT NULL,
                    severity         TEXT NOT NULL,  -- 'warning' | 'critical'
                    message          TEXT NOT NULL,
                    context          TEXT,           -- JSON with extra data
                    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                    acknowledged_at  TEXT,
                    acknowledged_by  TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_type       ON alerts(alert_type);
                CREATE INDEX IF NOT EXISTS idx_alerts_severity   ON alerts(severity);
                CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_alerts_unacked     ON alerts(acknowledged_at)
                    WHERE acknowledged_at IS NULL;
            """)
            await db.commit()

        # ── Migrate existing prediction_log tables (add new columns if missing) ──
        # Column names and types are defined here (never user-supplied) so the
        # f-string is safe. The allowlist check below guards against future drift.
        _ALLOWED_MIGRATION_COLS: dict = {
            "agent_bullish":       "INTEGER",
            "agent_bearish":       "INTEGER",
            "agent_neutral":       "INTEGER",
            "trend_label":         "TEXT",
            "actual_close_price":  "REAL",
            "resolved_at":         "TEXT",
            "resolution_notes":    "TEXT",
            "excluded_from_stats": "INTEGER DEFAULT 0",
            "exclusion_reason":    "TEXT",
        }
        new_cols = list(_ALLOWED_MIGRATION_COLS.items())
        async with aiosqlite.connect(DB_PATH) as db:
            for col, col_type in new_cols:
                if col not in _ALLOWED_MIGRATION_COLS or _ALLOWED_MIGRATION_COLS[col] != col_type:
                    logger.error("Migration skipped: column '%s' not in allowlist", col)
                    continue
                try:
                    await db.execute(f"ALTER TABLE prediction_log ADD COLUMN {col} {col_type}")
                    await db.commit()
                    logger.info("Migrated prediction_log: added column %s", col)
                except Exception:
                    pass  # Column already exists

        # ── Migrate simulations table: add full_json for restart recovery ────
        async with aiosqlite.connect(DB_PATH) as db:
            try:
                await db.execute("ALTER TABLE simulations ADD COLUMN full_json TEXT")
                await db.commit()
                logger.info("Migrated simulations: added full_json column")
            except Exception:
                pass  # Already exists

        _initialized = True
        logger.info("Database initialised at %s", DB_PATH)


# ── Prediction quality gate ────────────────────────────────────────────────────

# Predictions below this confidence are "noise" — the system is saying it
# cannot form a view. They are logged for traceability but excluded from
# public accuracy stats.
_MIN_STAT_CONFIDENCE = 0.05   # 5%


def _is_garbage_prediction(direction: str, confidence: float) -> Optional[str]:
    """
    Return an exclusion reason string if this prediction is garbage, else None.

    Garbage means the system had no real signal:
      - Confidence exactly 0 (minimum-confidence guard forced neutral)
      - Confidence < 5% AND direction is neutral (no view at all)
      - Confidence < 5% regardless of direction (below noise floor)
    """
    if confidence <= 0.0:
        return "Zero confidence — no signal (minimum confidence guard triggered)"
    if confidence < _MIN_STAT_CONFIDENCE:
        return f"Confidence {confidence*100:.1f}% below minimum {_MIN_STAT_CONFIDENCE*100:.0f}% threshold"
    return None


async def mark_existing_garbage_predictions() -> int:
    """
    One-time backfill: mark pre-existing garbage predictions as excluded.
    Safe to call on every startup (only updates rows not already marked).
    Returns count of newly marked rows.
    """
    try:
        await init_db()
        async with get_db() as db:
            result = await db.execute(
                """UPDATE prediction_log
                   SET excluded_from_stats = 1,
                       exclusion_reason = CASE
                           WHEN confidence <= 0.0 THEN 'Zero confidence — no signal (minimum confidence guard triggered)'
                           ELSE 'Confidence below 5% minimum threshold'
                       END
                   WHERE confidence < ?
                     AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)""",
                (_MIN_STAT_CONFIDENCE,),
            )
            await db.commit()
            n = result.rowcount
        if n:
            logger.info("Marked %d existing garbage predictions as excluded_from_stats", n)
        return n
    except Exception as e:
        logger.error("mark_existing_garbage_predictions failed: %s", e)
        return 0


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

        p        = prediction if isinstance(prediction, dict) else prediction.model_dump(mode="json")
        check_at = int(time.time()) + 86400

        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO simulations
                   (id, ticker, direction, confidence, event_description, event_type,
                    country, causal_chain, agent_votes, execution_time,
                    ticker_confidence, ticker_reasoning, outcome, check_at, created_at,
                    full_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    json.dumps(p),
                ),
            )
            await db.commit()
        logger.info("Saved simulation %s to simulations table", simulation_id)
    except Exception as e:
        logger.error("Failed to save simulation %s: %s", simulation_id, e)


async def get_simulation_full_json(simulation_id: str) -> Optional[dict]:
    """Recover a completed simulation's full prediction JSON from SQLite.
    Used to resurrect simulations lost from in-memory store after a server restart.
    Returns None if not found or full_json column is empty.
    """
    try:
        await init_db()
        import json as _json
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
            async with db.execute(
                "SELECT full_json FROM simulations WHERE id = ?", (simulation_id,)
            ) as cur:
                row = await cur.fetchone()
        if row and row.get("full_json"):
            return _json.loads(row["full_json"])
    except Exception as e:
        logger.warning("get_simulation_full_json failed for %s: %s", simulation_id, e)
    return None


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
        where  = "WHERE prediction_correct IS NOT NULL AND excluded_from_stats = 0" + (" AND ticker=?" if ticker else "")
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
    """Save a full prediction to prediction_log. Called non-blocking after every simulation.

    Predictions below the minimum confidence threshold are logged for traceability
    but automatically excluded from public accuracy stats via excluded_from_stats=1.
    """
    try:
        await init_db()
        # Normalize direction to lowercase for consistency with reflection script
        pred_dir = {"UP": "bullish", "DOWN": "bearish", "NEUTRAL": "neutral"}.get(
            direction.upper(), direction.lower()
        )

        # Quality gate: detect and flag garbage predictions at write time
        exclusion_reason = _is_garbage_prediction(pred_dir, confidence)
        excluded = 1 if exclusion_reason else 0
        if excluded:
            logger.info(
                "prediction_log [%s] %s marked excluded: %s", simulation_id, ticker, exclusion_reason
            )

        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO prediction_log
                   (id, ticker, predicted_direction, confidence, predicted_at,
                    primary_reason,
                    iron_ore_at_prediction, audusd_at_prediction,
                    brent_at_prediction, bhp_price_at_prediction,
                    agent_bullish, agent_bearish, agent_neutral, trend_label,
                    excluded_from_stats, exclusion_reason)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    excluded,
                    exclusion_reason,
                )
            )
            await db.commit()
        logger.info("Saved prediction_log entry: %s (%s %s %.0f%%)%s",
                    simulation_id, ticker, pred_dir, confidence * 100,
                    " [EXCLUDED]" if excluded else "")
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


async def get_detailed_accuracy_stats(
    ticker: Optional[str] = None,
    days: int = 365,
) -> Dict[str, Any]:
    """
    Returns comprehensive accuracy stats including:
    - Overall accuracy
    - Breakdown by direction (bullish/bearish/neutral)
    - Breakdown by confidence band (0-25%, 25-50%, 50-75%, 75-100%)
    - Current streak and best streak

    Args:
        ticker: Optional ticker filter.
        days:   Look-back window in days (default 365 = all recent predictions).
    """
    try:
        await init_db()
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Quality filter: confidence >= 5% AND directional (not neutral).
        # Neutral predictions abstain — they are stored with prediction_correct=NULL
        # so they're already excluded by the IS NOT NULL check, but we also explicitly
        # exclude them from the total count so pending neutrals don't inflate totals.
        _quality = (
            f"confidence >= {_MIN_STAT_CONFIDENCE} "
            f"AND predicted_direction NOT IN ('neutral')"
        )
        base_where = f"WHERE prediction_correct IS NOT NULL AND predicted_at >= ? AND {_quality}"
        params: list = [since]
        if ticker:
            base_where += " AND ticker = ?"
            params.append(ticker)

        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

            # Total quality predictions (including unresolved) within the same window
            total_where = f"WHERE predicted_at >= ? AND {_quality}" + (" AND ticker=?" if ticker else "")
            total_params = [since, ticker] if ticker else [since]
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

            # Excluded predictions count (for UI transparency note)
            excl_where = (
                f"WHERE predicted_at >= ? AND confidence < {_MIN_STAT_CONFIDENCE}"
                + (" AND ticker=?" if ticker else "")
            )
            excl_params = [since, ticker] if ticker else [since]
            async with db.execute(
                f"SELECT COUNT(*) as n FROM prediction_log {excl_where}", excl_params
            ) as cur:
                excl_row = await cur.fetchone()
            excluded_count = excl_row["n"] if excl_row else 0

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
            "excluded_count":       excluded_count,
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
            "avg_confidence": 0, "excluded_count": 0,
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
                    None if prediction_correct is None else int(prediction_correct),
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


# ── reasoning_predictions table ───────────────────────────────────────────────

async def save_reasoning_prediction(
    prediction_id: str,
    stock_ticker: str,
    direction: str,
    recommendation: str,
    confidence_score: int,
    price_at_prediction: float,
    reasoning_output: dict,
    trade_execution: Optional[Dict[str, Any]] = None,
    entry_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit_1: Optional[float] = None,
    take_profit_2: Optional[float] = None,
    take_profit_3: Optional[float] = None,
    event_classification: Optional[Dict[str, Any]] = None,
    causal_chain: Optional[Dict[str, Any]] = None,
    market_context: Optional[Dict[str, Any]] = None,
    agent_consensus: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a Reasoning Synthesizer prediction for accuracy tracking."""
    try:
        import json
        await init_db()
        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO reasoning_predictions
                   (id, stock_ticker, direction, recommendation, confidence_score,
                    price_at_prediction, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3,
                    event_classification, causal_chain, market_context, agent_consensus,
                    reasoning_output, trade_execution)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    prediction_id, stock_ticker, direction, recommendation, confidence_score,
                    price_at_prediction, entry_price, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3,
                    json.dumps(event_classification) if event_classification else None,
                    json.dumps(causal_chain) if causal_chain else None,
                    json.dumps(market_context) if market_context else None,
                    json.dumps(agent_consensus) if agent_consensus else None,
                    json.dumps(reasoning_output),
                    json.dumps(trade_execution) if trade_execution else None,
                ),
            )
            await db.commit()
        logger.info("Saved reasoning prediction %s for %s", prediction_id, stock_ticker)
    except Exception as e:
        logger.error("save_reasoning_prediction failed for %s: %s", prediction_id, e)


async def update_reasoning_outcome(
    prediction_id: str,
    outcome_status: str,
    actual_return_pct: float,
    hit_tp1: bool,
    hit_tp2: bool,
    hit_tp3: bool,
    hit_stop_loss: bool,
) -> None:
    """Update outcome for a reasoning prediction after price check."""
    try:
        from datetime import timezone
        await init_db()
        async with get_db() as db:
            await db.execute(
                """UPDATE reasoning_predictions
                   SET outcome_status=?, outcome_timestamp=?, actual_return_pct=?,
                       hit_tp1=?, hit_tp2=?, hit_tp3=?, hit_stop_loss=?,
                       updated_at=datetime('now')
                   WHERE id=?""",
                (
                    outcome_status,
                    datetime.now(timezone.utc).isoformat(),
                    round(actual_return_pct, 4),
                    int(hit_tp1), int(hit_tp2), int(hit_tp3), int(hit_stop_loss),
                    prediction_id,
                ),
            )
            await db.commit()
        logger.info("Updated outcome for reasoning prediction %s: %s", prediction_id, outcome_status)
    except Exception as e:
        logger.error("update_reasoning_outcome failed for %s: %s", prediction_id, e)


async def get_reasoning_accuracy_stats(
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    days: int = 90,
) -> Dict[str, Any]:
    """Return accuracy stats for reasoning predictions."""
    try:
        await init_db()
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).isoformat()

        conditions = ["prediction_timestamp >= ?"]
        params: list = [since]
        if ticker:
            conditions.append("stock_ticker = ?")
            params.append(ticker)
        if direction:
            conditions.append("direction = ?")
            params.append(direction)

        where = " AND ".join(conditions)

        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

            async with db.execute(
                f"""SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN outcome_status != 'PENDING' THEN 1 END) as resolved,
                    COUNT(CASE WHEN outcome_status = 'CORRECT'     THEN 1 END) as correct,
                    COUNT(CASE WHEN outcome_status = 'INCORRECT'   THEN 1 END) as incorrect,
                    COUNT(CASE WHEN outcome_status = 'PARTIAL'     THEN 1 END) as partial,
                    COUNT(CASE WHEN outcome_status = 'STOPPED_OUT' THEN 1 END) as stopped_out,
                    AVG(CASE WHEN outcome_status != 'PENDING' THEN actual_return_pct END) as avg_return,
                    AVG(confidence_score) as avg_confidence
                FROM reasoning_predictions WHERE {where}""",
                params,
            ) as cur:
                row = await cur.fetchone()

        resolved = row["resolved"] or 0
        correct = row["correct"] or 0
        accuracy = round(correct / resolved * 100, 2) if resolved > 0 else 0.0

        return {
            "scope": ticker or direction or "overall",
            "total_predictions": row["total"] or 0,
            "resolved_predictions": resolved,
            "correct": correct,
            "incorrect": row["incorrect"] or 0,
            "partial": row["partial"] or 0,
            "stopped_out": row["stopped_out"] or 0,
            "accuracy_pct": accuracy,
            "avg_return_pct": round(row["avg_return"] or 0, 4),
            "avg_confidence": round(row["avg_confidence"] or 0, 2),
        }
    except Exception as e:
        logger.error("get_reasoning_accuracy_stats failed: %s", e)
        return {"scope": ticker or "overall", "error": str(e)}


async def get_reasoning_predictions_for_memory(
    ticker: str,
    direction: str,
    days: int = 180,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Fetch past resolved predictions for the prediction memory system."""
    try:
        import json
        await init_db()
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).isoformat()

        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT id, stock_ticker, direction, confidence_score,
                          outcome_status, actual_return_pct, event_classification,
                          causal_chain, prediction_timestamp
                   FROM reasoning_predictions
                   WHERE stock_ticker = ? AND direction = ?
                     AND outcome_status != 'PENDING'
                     AND prediction_timestamp >= ?
                   ORDER BY prediction_timestamp DESC
                   LIMIT ?""",
                (ticker, direction, since, limit),
            ) as cur:
                rows = await cur.fetchall()

        for row in rows:
            if row.get("event_classification"):
                try:
                    row["event_classification"] = json.loads(row["event_classification"])
                except Exception as e:
                    logger.debug("Failed to parse event_classification JSON for row %s: %s", row.get("id"), e)
        return rows
    except Exception as e:
        logger.error("get_reasoning_predictions_for_memory failed: %s", e)
        return []


async def get_pending_reasoning_predictions(limit: int = 100) -> List[Dict[str, Any]]:
    """Return PENDING predictions older than 1 day for outcome resolution."""
    try:
        await init_db()
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT id, stock_ticker, direction, price_at_prediction,
                          stop_loss, take_profit_1, take_profit_2, take_profit_3,
                          prediction_timestamp
                   FROM reasoning_predictions
                   WHERE outcome_status = 'PENDING'
                     AND prediction_timestamp < datetime('now', '-1 day')
                   ORDER BY prediction_timestamp ASC
                   LIMIT ?""",
                (limit,),
            ) as cur:
                return await cur.fetchall()
    except Exception as e:
        logger.error("get_pending_reasoning_predictions failed: %s", e)
        return []
