-- ═══════════════════════════════════════════════════════════════════════════
-- Market Oracle AI — PostgreSQL initial schema
-- Migration: 001_initial_schema
-- Converts from SQLite; safe to run against a blank DB.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── Migration tracking ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── simulations ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS simulations (
    id                  TEXT PRIMARY KEY,
    ticker              TEXT NOT NULL,
    direction           TEXT NOT NULL,
    confidence          DOUBLE PRECISION,
    event_description   TEXT,
    event_type          TEXT,
    country             TEXT,
    causal_chain        TEXT,
    agent_votes         TEXT,
    execution_time      DOUBLE PRECISION,
    ticker_confidence   DOUBLE PRECISION,
    ticker_reasoning    TEXT,
    outcome             TEXT,
    check_at            BIGINT,
    actual_change_pct   DOUBLE PRECISION,
    full_json           TEXT,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_ticker   ON simulations(ticker);
CREATE INDEX IF NOT EXISTS idx_sim_created  ON simulations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sim_check_at ON simulations(check_at);

-- ── events ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    id             TEXT PRIMARY KEY,
    acled_event_id TEXT,
    country        TEXT,
    event_type     TEXT,
    lat            DOUBLE PRECISION,
    lon            DOUBLE PRECISION,
    fatalities     INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL
);

-- ── prediction_log ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prediction_log (
    id                      TEXT PRIMARY KEY,
    ticker                  TEXT NOT NULL,
    predicted_direction     TEXT NOT NULL,
    confidence              DOUBLE PRECISION,
    predicted_at            TEXT NOT NULL,
    primary_reason          TEXT,

    -- Market snapshot
    iron_ore_at_prediction  DOUBLE PRECISION,
    audusd_at_prediction    DOUBLE PRECISION,
    brent_at_prediction     DOUBLE PRECISION,
    bhp_price_at_prediction DOUBLE PRECISION,

    -- Agent vote counts
    agent_bullish           INTEGER,
    agent_bearish           INTEGER,
    agent_neutral           INTEGER,

    -- Trend context
    trend_label             TEXT,

    -- Reflection fields
    actual_direction        TEXT,
    actual_close_price      DOUBLE PRECISION,
    actual_price_change_pct DOUBLE PRECISION,
    prediction_correct      INTEGER,
    actual_driver           TEXT,
    reason_matched          INTEGER,
    lesson                  TEXT,
    resolved_at             TEXT,
    resolution_notes        TEXT,

    -- Quality gate
    excluded_from_stats     INTEGER DEFAULT 0,
    exclusion_reason        TEXT,

    created_at              TEXT NOT NULL DEFAULT (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))
);

CREATE INDEX IF NOT EXISTS idx_log_ticker          ON prediction_log(ticker);
CREATE INDEX IF NOT EXISTS idx_log_predicted_at    ON prediction_log(predicted_at DESC);
-- PostgreSQL supports partial indexes with WHERE
CREATE INDEX IF NOT EXISTS idx_log_unresolved      ON prediction_log(actual_direction)
    WHERE actual_direction IS NULL;

-- ── reasoning_predictions ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reasoning_predictions (
    id                   TEXT PRIMARY KEY,
    stock_ticker         TEXT NOT NULL,
    prediction_timestamp TEXT NOT NULL DEFAULT (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
    direction            TEXT NOT NULL,
    recommendation       TEXT NOT NULL,
    confidence_score     INTEGER NOT NULL,
    price_at_prediction  DOUBLE PRECISION NOT NULL,

    -- Trade execution
    entry_price          DOUBLE PRECISION,
    stop_loss            DOUBLE PRECISION,
    take_profit_1        DOUBLE PRECISION,
    take_profit_2        DOUBLE PRECISION,
    take_profit_3        DOUBLE PRECISION,

    -- Outcome tracking
    outcome_status       TEXT NOT NULL DEFAULT 'PENDING',
    outcome_timestamp    TEXT,
    actual_return_pct    DOUBLE PRECISION,
    hit_tp1              INTEGER DEFAULT 0,
    hit_tp2              INTEGER DEFAULT 0,
    hit_tp3              INTEGER DEFAULT 0,
    hit_stop_loss        INTEGER DEFAULT 0,

    -- Price checkpoints
    price_1d             DOUBLE PRECISION,
    price_7d             DOUBLE PRECISION,
    price_30d            DOUBLE PRECISION,

    -- Context (JSON)
    event_classification TEXT,
    causal_chain         TEXT,
    market_context       TEXT,
    agent_consensus      TEXT,
    reasoning_output     TEXT NOT NULL,
    trade_execution      TEXT,

    created_at           TEXT NOT NULL DEFAULT (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
    updated_at           TEXT NOT NULL DEFAULT (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'))
);

CREATE INDEX IF NOT EXISTS idx_rp_ticker    ON reasoning_predictions(stock_ticker);
CREATE INDEX IF NOT EXISTS idx_rp_timestamp ON reasoning_predictions(prediction_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_rp_outcome   ON reasoning_predictions(outcome_status);
CREATE INDEX IF NOT EXISTS idx_rp_direction ON reasoning_predictions(direction);

-- ── alerts ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alerts (
    id               BIGSERIAL PRIMARY KEY,
    alert_type       TEXT NOT NULL,
    severity         TEXT NOT NULL,
    message          TEXT NOT NULL,
    context          TEXT,
    created_at       TEXT NOT NULL DEFAULT (to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')),
    acknowledged_at  TEXT,
    acknowledged_by  TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_type       ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity   ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unacked    ON alerts(acknowledged_at)
    WHERE acknowledged_at IS NULL;

-- Mark this migration as applied
INSERT INTO schema_migrations (version) VALUES ('001_initial_schema')
    ON CONFLICT (version) DO NOTHING;
