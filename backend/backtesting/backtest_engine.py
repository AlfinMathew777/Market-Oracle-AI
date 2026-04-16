"""
Historical backtesting engine for Market Oracle AI.

Replays historical ASX price data through a technical signal predictor
(RSI + SMA crossover + volume confirmation) to measure directional accuracy
before relying on live predictions in production.

CRITICAL — no look-ahead bias:
  For any prediction on date D, only price data from dates strictly BEFORE D
  is ever accessed. The target day and all future dates are invisible to the
  signal generator. Enforced by df[df.index < target_date] in every code path.
"""

import asyncio
import json
import logging
import math
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import aiosqlite
import pandas as pd

from database import DB_PATH, init_db

logger = logging.getLogger(__name__)

# ── Table DDL ──────────────────────────────────────────────────────────────────

_BACKTEST_DDL = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT UNIQUE NOT NULL,
    config       TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    started_at   TEXT,
    completed_at TEXT,
    metrics      TEXT,
    error        TEXT,
    progress     INTEGER DEFAULT 0,
    total_steps  INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bt_run_id ON backtest_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_bt_status  ON backtest_runs(status);

CREATE TABLE IF NOT EXISTS backtest_predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    prediction_date TEXT NOT NULL,
    ticker          TEXT NOT NULL,
    direction       TEXT NOT NULL,
    confidence      REAL NOT NULL,
    entry_price     REAL,
    exit_price      REAL,
    change_pct      REAL,
    outcome         TEXT,
    FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_btp_run_id ON backtest_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_btp_ticker ON backtest_predictions(ticker);
CREATE INDEX IF NOT EXISTS idx_btp_date   ON backtest_predictions(prediction_date);
"""


async def init_backtest_tables() -> None:
    """Create backtest tables if they don't exist. Safe to call multiple times."""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_BACKTEST_DDL)
        await db.commit()
    logger.debug("Backtest tables ready")


# ── Dataclasses (frozen = immutable) ──────────────────────────────────────────

@dataclass(frozen=True)
class BacktestConfig:
    tickers: tuple[str, ...]  # immutable; caller converts list → tuple
    start_date: str           # YYYY-MM-DD
    end_date: str             # YYYY-MM-DD
    lookback_days: int = 30


@dataclass(frozen=True)
class BacktestPrediction:
    date: str
    ticker: str
    direction: str   # UP | DOWN | NEUTRAL
    confidence: float
    entry_price: float
    exit_price: float
    change_pct: float
    outcome: str     # CORRECT | INCORRECT | NEUTRAL


@dataclass(frozen=True)
class BacktestMetrics:
    total_predictions: int
    correct: int
    incorrect: int
    neutral: int
    hit_rate: float
    hit_rate_by_confidence: dict
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float


@dataclass
class BacktestResult:
    run_id: str
    config: BacktestConfig
    predictions: list[BacktestPrediction]
    metrics: BacktestMetrics


# ── ASX trading-day filter ─────────────────────────────────────────────────────

# National public holidays observed by the ASX — approximate list for 2024-2025.
# The yfinance data itself will have gaps on real holidays, but this set lets
# the backtest loop skip them without needing to fetch a full calendar.
_ASX_HOLIDAYS: frozenset[date] = frozenset({
    # 2024
    date(2024, 1, 1), date(2024, 1, 26), date(2024, 3, 29),
    date(2024, 3, 30), date(2024, 4, 1), date(2024, 4, 25),
    date(2024, 6, 10), date(2024, 12, 25), date(2024, 12, 26),
    # 2025
    date(2025, 1, 1), date(2025, 1, 27), date(2025, 4, 18),
    date(2025, 4, 19), date(2025, 4, 21), date(2025, 4, 25),
    date(2025, 6, 9), date(2025, 12, 25), date(2025, 12, 26),
})


def is_trading_day(dt: datetime) -> bool:
    """Return True if the ASX is open (Mon–Fri, not a public holiday)."""
    d = dt.date() if isinstance(dt, datetime) else dt
    return d.weekday() < 5 and d not in _ASX_HOLIDAYS


# ── Data fetching ──────────────────────────────────────────────────────────────

async def fetch_historical_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch OHLCV data from yfinance.

    Fetches a 90-day buffer before *start* so the lookback window has enough
    data even on the very first prediction date.

    Returns a DataFrame indexed by normalized UTC timestamps, with columns:
    Open, High, Low, Close, Volume.
    """
    import yfinance as yf

    buf_start = (
        datetime.strptime(start, "%Y-%m-%d") - timedelta(days=90)
    ).strftime("%Y-%m-%d")

    def _fetch() -> pd.DataFrame:
        df = yf.Ticker(ticker).history(start=buf_start, end=end, interval="1d")
        if df.empty:
            raise ValueError(f"yfinance returned no data for {ticker}")
        df.index = pd.to_datetime(df.index).normalize()
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch)


# ── Technical signal ───────────────────────────────────────────────────────────

def _compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """Wilder RSI. Returns 50.0 (neutral) if there is insufficient data."""
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff().dropna()
    avg_gain = delta.clip(lower=0).tail(period).mean()
    avg_loss = (-delta).clip(lower=0).tail(period).mean()
    if avg_loss == 0:
        return 100.0
    return round(100.0 - 100.0 / (1.0 + avg_gain / avg_loss), 2)


def _generate_signal(
    df: pd.DataFrame,
    target_date: pd.Timestamp,
    lookback_days: int,
) -> tuple[str, float]:
    """
    Generate a directional signal using only data strictly before *target_date*.

    Three independent sub-signals are combined:
      1. RSI(14)            — oversold (<30) bullish, overbought (>70) bearish
      2. SMA(5) / SMA(20)   — golden/death cross
      3. Volume spike       — above-average volume confirms the SMA direction

    Confidence is mapped from signal agreement into [0.35, 0.75] to respect
    the system-wide confidence caps (hard cap 85%, primary order max 75%).
    """
    # ── Look-ahead guard ──────────────────────────────────────────────────────
    past = df[df.index < target_date].tail(lookback_days + 30)

    if len(past) < 20:
        return "NEUTRAL", 0.30

    closes = past["Close"]
    volume = past["Volume"]

    rsi = _compute_rsi(closes, period=14)
    sma5 = float(closes.tail(5).mean())
    sma20 = float(closes.tail(20).mean())
    sma_bull = sma5 > sma20

    vol_avg = float(volume.tail(20).mean())
    vol_spike = float(volume.iloc[-1]) > vol_avg * 1.2

    bull = 0
    bear = 0

    if rsi < 30:
        bull += 2
    elif rsi < 45:
        bull += 1
    elif rsi > 70:
        bear += 2
    elif rsi > 55:
        bear += 1

    if sma_bull:
        bull += 1
    else:
        bear += 1

    if vol_spike and sma_bull:
        bull += 1
    elif vol_spike and not sma_bull:
        bear += 1

    diff = bull - bear
    if diff == 0:
        return "NEUTRAL", 0.30

    # Scale to [0.35, 0.75]
    confidence = max(0.35, min(0.75, 0.35 + abs(diff) / 4.0 * 0.40))
    direction = "UP" if diff > 0 else "DOWN"
    return direction, round(confidence, 3)


# ── Outcome labelling ──────────────────────────────────────────────────────────

_NOISE_THRESHOLD_PCT = 0.5  # moves within ±0.5% are market noise


def _determine_outcome(direction: str, change_pct: float) -> str:
    """CORRECT if direction matches next-day move; NEUTRAL if within noise band."""
    if abs(change_pct) < _NOISE_THRESHOLD_PCT or direction == "NEUTRAL":
        return "NEUTRAL"
    if direction == "UP" and change_pct > 0:
        return "CORRECT"
    if direction == "DOWN" and change_pct < 0:
        return "CORRECT"
    return "INCORRECT"


# ── Metrics ────────────────────────────────────────────────────────────────────

def calculate_metrics(predictions: list[BacktestPrediction]) -> BacktestMetrics:
    """
    Aggregate hit rate, Sharpe ratio, max drawdown, and profit factor.

    Neutral-direction predictions are excluded from directional stats.
    Neutral *outcomes* (within noise band) are counted separately and do
    not penalise the hit rate.
    """
    directional = [p for p in predictions if p.direction != "NEUTRAL"]
    total = len(directional)
    correct = sum(1 for p in directional if p.outcome == "CORRECT")
    incorrect = sum(1 for p in directional if p.outcome == "INCORRECT")
    neutral_outcomes = sum(1 for p in predictions if p.outcome == "NEUTRAL")

    hit_rate = round(correct / total, 3) if total > 0 else 0.0

    # Hit rate by confidence band
    bands = {
        "0-25%":   (0.00, 0.25),
        "25-50%":  (0.25, 0.50),
        "50-75%":  (0.50, 0.75),
        "75-100%": (0.75, 1.01),
    }
    hit_rate_by_confidence: dict = {}
    for label, (lo, hi) in bands.items():
        band = [p for p in directional if lo <= p.confidence < hi]
        band_correct = sum(1 for p in band if p.outcome == "CORRECT")
        hit_rate_by_confidence[label] = {
            "total": len(band),
            "correct": band_correct,
            "hit_rate": round(band_correct / len(band), 3) if band else 0.0,
        }

    # Simulated daily return series
    # Long when UP, short when DOWN — measures signal quality, not portfolio P&L.
    daily_returns = []
    for p in directional:
        if p.entry_price and p.entry_price > 0:
            raw = p.change_pct / 100.0
            daily_returns.append(raw if p.direction == "UP" else -raw)

    sharpe = _compute_sharpe(daily_returns)
    max_dd = _compute_max_drawdown(daily_returns)

    gains = sum(r for r in daily_returns if r > 0)
    losses = sum(abs(r) for r in daily_returns if r < 0)
    profit_factor = round(gains / losses, 3) if losses > 0 else 0.0

    return BacktestMetrics(
        total_predictions=total,
        correct=correct,
        incorrect=incorrect,
        neutral=neutral_outcomes,
        hit_rate=hit_rate,
        hit_rate_by_confidence=hit_rate_by_confidence,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        profit_factor=profit_factor,
    )


def _compute_sharpe(returns: list[float], risk_free: float = 0.0) -> float:
    """Annualised Sharpe ratio (252 trading days)."""
    if len(returns) < 2:
        return 0.0
    import statistics
    std = statistics.stdev(returns)
    if std == 0:
        return 0.0
    return round((statistics.mean(returns) - risk_free) / std * math.sqrt(252), 3)


def _compute_max_drawdown(returns: list[float]) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction."""
    if not returns:
        return 0.0
    cumulative = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        cumulative *= 1.0 + r
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


# ── DB persistence helpers ─────────────────────────────────────────────────────

async def _create_run(run_id: str, config: BacktestConfig, total_steps: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO backtest_runs
               (run_id, config, status, started_at, total_steps, progress)
               VALUES (?, ?, 'running', ?, ?, 0)""",
            (
                run_id,
                json.dumps({
                    "tickers": list(config.tickers),
                    "start_date": config.start_date,
                    "end_date": config.end_date,
                    "lookback_days": config.lookback_days,
                }),
                datetime.now(timezone.utc).isoformat(),
                total_steps,
            ),
        )
        await db.commit()


async def _update_progress(run_id: str, progress: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE backtest_runs SET progress = ? WHERE run_id = ?",
            (progress, run_id),
        )
        await db.commit()


async def _complete_run(run_id: str, metrics: BacktestMetrics) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE backtest_runs
               SET status='completed', completed_at=?, metrics=?,
                   progress=total_steps
               WHERE run_id=?""",
            (
                datetime.now(timezone.utc).isoformat(),
                json.dumps(asdict(metrics)),
                run_id,
            ),
        )
        await db.commit()


async def _fail_run(run_id: str, error: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE backtest_runs
               SET status='failed', completed_at=?, error=?
               WHERE run_id=?""",
            (datetime.now(timezone.utc).isoformat(), error[:1000], run_id),
        )
        await db.commit()


async def _bulk_save_predictions(
    run_id: str,
    predictions: list[BacktestPrediction],
) -> None:
    """Bulk-insert all predictions in a single transaction."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT INTO backtest_predictions
               (run_id, prediction_date, ticker, direction, confidence,
                entry_price, exit_price, change_pct, outcome)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    run_id, p.date, p.ticker, p.direction,
                    p.confidence, p.entry_price, p.exit_price,
                    p.change_pct, p.outcome,
                )
                for p in predictions
            ],
        )
        await db.commit()


# ── Public read helpers (used by routes) ──────────────────────────────────────

async def get_run_status(run_id: str) -> Optional[dict]:
    """Return status row for a run, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))
        async with db.execute(
            "SELECT * FROM backtest_runs WHERE run_id = ?", (run_id,)
        ) as cur:
            return await cur.fetchone()


async def get_run_predictions(
    run_id: str,
    page: int = 1,
    page_size: int = 100,
    ticker: Optional[str] = None,
) -> tuple[list[dict], int]:
    """
    Return paginated predictions for a run.

    Returns (rows, total_count).
    """
    conditions = ["run_id = ?"]
    params: list = [run_id]
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)

    where = " AND ".join(conditions)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = lambda c, r: dict(zip([d[0] for d in c.description], r))

        async with db.execute(
            f"SELECT COUNT(*) as n FROM backtest_predictions WHERE {where}",
            params,
        ) as cur:
            total_row = await cur.fetchone()
        total = total_row["n"] if total_row else 0

        offset = (page - 1) * page_size
        async with db.execute(
            f"""SELECT * FROM backtest_predictions WHERE {where}
                ORDER BY prediction_date ASC, ticker ASC
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ) as cur:
            rows = await cur.fetchall()

    return rows, total


# ── Main backtest loop ─────────────────────────────────────────────────────────

def generate_run_id() -> str:
    """Generate a unique backtest run ID."""
    return f"bt_{uuid.uuid4().hex[:12]}"


async def run_backtest(
    config: BacktestConfig,
    run_id: Optional[str] = None,
) -> BacktestResult:
    """
    Run a full backtest and persist results to the database.

    Algorithm:
      1. Enumerate ASX trading days in [start_date, end_date].
      2. Fetch OHLCV data for every ticker upfront (with delay between calls
         to respect yfinance rate limits).
      3. For each (ticker, day):
           a. Slice df strictly before that day — no look-ahead.
           b. Derive direction + confidence from RSI/SMA/volume.
           c. Compute actual next-day return.
           d. Label outcome as CORRECT / INCORRECT / NEUTRAL.
      4. Calculate aggregate metrics.
      5. Bulk-persist predictions and mark run as completed.

    If *run_id* is supplied the caller has already created the DB row via
    _create_run(); otherwise a new row is created here.

    Progress is written to the DB every 50 steps for polling by the status
    endpoint. Yields to the event loop on every batch so the server stays
    responsive during long backtests.
    """
    if run_id is None:
        run_id = generate_run_id()
        await init_backtest_tables()

    start_dt = datetime.strptime(config.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(config.end_date, "%Y-%m-%d")

    trading_days: list[datetime] = []
    cursor = start_dt
    while cursor <= end_dt:
        if is_trading_day(cursor):
            trading_days.append(cursor)
        cursor += timedelta(days=1)

    total_steps = len(trading_days) * len(config.tickers)
    await _create_run(run_id, config, total_steps)

    logger.info(
        "Backtest %s started — %d tickers × %d trading days = %d steps",
        run_id, len(config.tickers), len(trading_days), total_steps,
    )

    try:
        # ── Phase 1: fetch all data upfront ───────────────────────────────────
        ticker_data: dict[str, pd.DataFrame] = {}
        for i, ticker in enumerate(config.tickers):
            try:
                df = await fetch_historical_data(
                    ticker, config.start_date, config.end_date
                )
                ticker_data[ticker] = df
                logger.info("Fetched %s: %d rows", ticker, len(df))
            except Exception as exc:
                logger.warning("Skipping %s — fetch failed: %s", ticker, exc)
            # Rate-limit gap between yfinance requests
            if i < len(config.tickers) - 1:
                await asyncio.sleep(1.5)

        if not ticker_data:
            raise RuntimeError("No ticker data could be fetched — aborting")

        # ── Phase 2: generate predictions ─────────────────────────────────────
        predictions: list[BacktestPrediction] = []
        step = 0

        for ticker, df in ticker_data.items():
            for day in trading_days:
                day_ts = pd.Timestamp(day)

                # ── Look-ahead guard (primary) ─────────────────────────────────
                past = df[df.index < day_ts]
                if len(past) < 20:
                    step += 1
                    continue

                # Entry = open on prediction day; skip if no market data for day
                day_row = df[df.index == day_ts]
                if day_row.empty:
                    step += 1
                    continue
                entry_price = float(day_row["Open"].iloc[0])

                # Exit = close of the next available trading day
                future = df[df.index > day_ts]
                if future.empty:
                    step += 1
                    continue
                exit_price = float(future["Close"].iloc[0])
                change_pct = (exit_price - entry_price) / entry_price * 100.0

                direction, confidence = _generate_signal(
                    df, day_ts, config.lookback_days
                )
                outcome = _determine_outcome(direction, change_pct)

                predictions.append(
                    BacktestPrediction(
                        date=day.strftime("%Y-%m-%d"),
                        ticker=ticker,
                        direction=direction,
                        confidence=confidence,
                        entry_price=round(entry_price, 4),
                        exit_price=round(exit_price, 4),
                        change_pct=round(change_pct, 4),
                        outcome=outcome,
                    )
                )

                step += 1
                # Persist progress and yield every 50 steps
                if step % 50 == 0:
                    await _update_progress(run_id, step)
                    await asyncio.sleep(0)  # yield to event loop

        # ── Phase 3: metrics + persist ─────────────────────────────────────────
        metrics = calculate_metrics(predictions)
        await _bulk_save_predictions(run_id, predictions)
        await _complete_run(run_id, metrics)

        logger.info(
            "Backtest %s complete — %d predictions, hit_rate=%.1f%%, "
            "sharpe=%.2f, max_dd=%.1f%%",
            run_id,
            metrics.total_predictions,
            metrics.hit_rate * 100,
            metrics.sharpe_ratio,
            metrics.max_drawdown * 100,
        )

        return BacktestResult(
            run_id=run_id,
            config=config,
            predictions=predictions,
            metrics=metrics,
        )

    except Exception as exc:
        logger.error("Backtest %s failed: %s", run_id, exc, exc_info=True)
        await _fail_run(run_id, str(exc))
        raise
