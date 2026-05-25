-- ═══════════════════════════════════════════════════════════════════════════
-- Market Oracle AI — Dream-cycle experiment scaffolding
-- Migration: 002_experiment_arm
--
-- Adds the columns and table needed to run the prediction-level A/B trial
-- described in docs/analysis_plan.md. This migration is data-only — it adds
-- storage but does NOT yet inject lessons into the simulation pipeline.
--
-- Backfill: experiment_arm is NULL for all existing rows. The /api/simulate
-- write path will start populating it on the next prediction.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── prediction_log: experiment instrumentation ──────────────────────────────
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS experiment_arm    TEXT;
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS model_used        TEXT;
ALTER TABLE prediction_log ADD COLUMN IF NOT EXISTS raw_prompt_hash   TEXT;

CREATE INDEX IF NOT EXISTS idx_log_experiment_arm
    ON prediction_log(experiment_arm)
    WHERE experiment_arm IS NOT NULL;

-- ── agent_lessons: dream-cycle output store ─────────────────────────────────
-- Each row is one human-reviewed corrective rule produced by the nightly
-- clustering job. status='active' means the rule is eligible for injection;
-- effective_from is the leakage guard — a lesson may never be applied to a
-- prediction whose created_at predates it.
CREATE TABLE IF NOT EXISTS agent_lessons (
    id                  TEXT PRIMARY KEY,
    lesson_text         TEXT NOT NULL,
    cluster_id          TEXT,               -- groups lessons from the same failure cluster
    sector              TEXT,               -- NULL = applies to all sectors
    priority            INTEGER DEFAULT 0,  -- higher = injected first when K caps
    status              TEXT NOT NULL DEFAULT 'pending_approval',
                        -- 'pending_approval' | 'active' | 'inactive' | 'rejected'
    effective_from      TIMESTAMPTZ,        -- NULL until activated
    approved_by         TEXT,
    approved_at         TIMESTAMPTZ,
    deactivated_at      TIMESTAMPTZ,
    deactivation_reason TEXT,
    source_prediction_ids TEXT,             -- JSON array of prediction_log.id rows used as evidence
    raw_llm_reasoning   TEXT,               -- the LLM output that generated this lesson
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lessons_status
    ON agent_lessons(status, effective_from)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_lessons_sector ON agent_lessons(sector);
CREATE INDEX IF NOT EXISTS idx_lessons_cluster ON agent_lessons(cluster_id);
