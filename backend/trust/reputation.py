"""Canonical learned-reputation store for sources and agent archetypes.

This is the single reputation system for the project — the future I4 input-trust
layer reads `min_source_reputation` from here rather than a static constant.

Two identities are tracked:
  - source_id  : stable external origin (news outlet, gdelt, acled, reddit, ...)
  - archetype  : one of the 4 voting roles (macro_bull/geo_bear/quant/neutral_fund),
                 keyed jointly with the market regime — see Decision 1 below.

Agent reputation is keyed by (ARCHETYPE, REGIME), never by per-run agent_id. It
measures ARCHETYPE BIAS / CALIBRATION (how well a designed role is calibrated FOR
ITS ROLE within a regime), NOT security-trust — macro_bull is built to argue
bullish, so being "wrong" in a downtrend is its job, not evidence of compromise.
Do not wire this where security-trust is assumed.

Decision 1 (RESOLVED — Option B, regime-conditioned calibration): an archetype's
record is split by the regime it voted in, so "macro_bull in downtrend" and
"macro_bull in uptrend" are SEPARATE track records. regime is the EXISTING trend
bucket from get_persona_distribution (STRONG_UPTREND ... STRONG_DOWNTREND), reused
not reinvented. "Calibrated for its role within this regime" is a better-aligned
checker than "archetype right/wrong" — the latter is a drifted proxy the loop
would optimize into "agree with the trend," eroding the adversarial design.
source reputation stays regime-agnostic (regime="").

GUARANTEES (the loop can poison itself, so these are load-bearing):
  - per-identity min-sample gate — below MIN_SAMPLES, an identity sits on the
    neutral-low prior no matter what is stored, so a thin sample cannot swing it.
  - protective floor/ceiling — clamped to [FLOOR, CEILING]; nothing ever reaches
    0 (permanent silence) or 1 (blind trust). The floor is genuinely protective:
    a chronically-wrong archetype still keeps FLOOR weight and is never silenced.
  - reputation only caps/weights; it never hard-blocks (that stays with I-layer
    rules).
  - two-step fallback (effective_archetype) — splitting the thin 4-archetype data
    into regime cells makes most cells cold for a long time, so the gate is more
    load-bearing, not less. A thin (archetype, regime) cell falls back to the
    archetype's pooled (regime-agnostic) record, then to the static prior. No
    value that skipped the gate is ever returned.

GOODHART GUARD (the checker must be ungameable from inside): archetype agents
NEVER see reputation in their prompt or context — it weights the vote at
reconciliation time only. If a score entered an agent's context the agent would
optimize to the score instead of reasoning honestly. Nothing here is read into
agent prompt construction; keep it that way.

RESIDUAL (do NOT implement — future Byzantine layer): an attacker who learns this
checker can satisfy it while corrupting the prediction — "who verifies the
verifier." That is the known residual, deferred to a later trust layer.

Persistence mirrors the trust ledger: stdlib sqlite3 off the event loop, so the
store has no extra dependency and works in tests without the app DB.

Piece 1 ships the store, reads, prior, gate, and the regime fallback. The
outcome-fed UPDATE RULE (EMA, survivorship, clamp) lands in Piece 2 — this module
deliberately contains no resolution hook yet.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# neutral-low cold start. future I4 min_source_reputation reads this value.
REPUTATION_PRIOR = 0.3
# protective bounds — never 0 (silence) or 1 (blind trust).
REPUTATION_FLOOR = 0.05
REPUTATION_CEILING = 0.95
# below this many resolved outcomes, return the prior regardless of stored value.
MIN_SAMPLES = 5

SOURCE = "source"
ARCHETYPE = "archetype"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source_reputation (
    source_id    TEXT NOT NULL,
    regime       TEXT NOT NULL DEFAULT '',
    reputation   REAL NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (source_id, regime)
);
CREATE TABLE IF NOT EXISTS agent_reputation (
    archetype    TEXT NOT NULL,
    regime       TEXT NOT NULL DEFAULT '',
    reputation   REAL NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (archetype, regime)
);
-- one row per (prediction, cell) it touched. lets a 7-day authoritative label
-- back out the provisional 24h delta and supersede it — never two stacked steps.
CREATE TABLE IF NOT EXISTS reputation_contribution (
    prediction_id TEXT NOT NULL,
    identity      TEXT NOT NULL,
    kind          TEXT NOT NULL,
    regime        TEXT NOT NULL DEFAULT '',
    applied_delta REAL NOT NULL,
    stage         TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (prediction_id, identity, kind, regime)
);
"""

# update stages — authoritative (7-day) supersedes provisional (24h).
STAGE_PROVISIONAL = "provisional"
STAGE_AUTHORITATIVE = "authoritative"

# read tiers — which fallback produced an effective score (debug/readability).
TIER_CELL = "cell"
TIER_ARCHETYPE_AGNOSTIC = "archetype_agnostic"
TIER_PRIOR = "prior"


def _clamp(value: float) -> float:
    return max(REPUTATION_FLOOR, min(REPUTATION_CEILING, value))


@dataclass(frozen=True)
class ReputationRecord:
    """One identity's stored reputation. `effective` applies the prior gate."""

    identity: str
    kind: str
    reputation: float
    sample_count: int
    regime: str = ""

    @property
    def is_seasoned(self) -> bool:
        return self.sample_count >= MIN_SAMPLES

    @property
    def effective(self) -> float:
        # thin sample → prior; the gate is what keeps early data from doing damage.
        if not self.is_seasoned:
            return REPUTATION_PRIOR
        return _clamp(self.reputation)


def _table(kind: str) -> str:
    if kind == SOURCE:
        return "source_reputation"
    if kind == ARCHETYPE:
        return "agent_reputation"
    raise ValueError(f"unknown reputation kind: {kind}")


def _id_column(kind: str) -> str:
    return "source_id" if kind == SOURCE else "archetype"


class ReputationStore:
    """Persistent source/archetype reputation — reads now, updates in Piece 2."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    async def record(self, identity: str, kind: str, regime: str = "") -> ReputationRecord:
        """Load one identity's reputation, or a cold-start prior record if unseen.

        Fail-soft: a read error returns the prior rather than raising, so a
        corrupt/missing store degrades to the static prior, never crashes a caller.
        """
        try:
            row = await asyncio.to_thread(self._load_sync, identity, kind, regime)
        except Exception as e:  # noqa: BLE001 — fall back to prior, never crash.
            logger.warning("reputation read failed for %s/%s (%s) — using prior", kind, identity, e)
            row = None
        if row is None:
            return ReputationRecord(identity, kind, REPUTATION_PRIOR, 0, regime)
        return ReputationRecord(
            identity=identity,
            kind=kind,
            reputation=float(row["reputation"]),
            sample_count=int(row["sample_count"]),
            regime=regime,
        )

    async def effective(self, identity: str, kind: str, regime: str = "") -> float:
        """Gated, clamped reputation a caller should weight by. Prior when thin."""
        rec = await self.record(identity, kind, regime)
        return rec.effective

    async def effective_archetype(self, archetype: str, regime: str = "") -> float:
        """Regime-conditioned archetype reputation with a two-step fallback.

        Decision 1 / Option B fallback order:
          1. (archetype, regime) cell — used only once it is SEASONED.
          2. (archetype, "")     pooled record — the archetype's regime-agnostic
             track record, used only once IT is seasoned.
          3. static prior        — when even the pooled record is thin.

        Each step requires its own min-sample gate to pass before its value is
        used; a thin cell never leaks a pre-gate number into the next step.
        """
        value, _ = await self.effective_with_tier(archetype, ARCHETYPE, regime)
        return value

    async def effective_with_tier(
        self, identity: str, kind: str, regime: str = "",
    ) -> tuple[float, str]:
        """Effective reputation plus the tier that produced it.

        source → cell or prior (regime-agnostic). archetype → the Option-B
        fallback: regime cell, then regime-agnostic pooled record, then prior.
        The tier makes the before/after table readable — you can see whether a
        score is real learning, the A-backstop, or still the cold-start prior.
        """
        if kind == SOURCE:
            rec = await self.record(identity, SOURCE, "")
            return (rec.effective, TIER_CELL if rec.is_seasoned else TIER_PRIOR)
        if regime:
            cell = await self.record(identity, ARCHETYPE, regime)
            if cell.is_seasoned:
                return (cell.effective, TIER_CELL)
        pooled = await self.record(identity, ARCHETYPE, "")
        if pooled.is_seasoned:
            return (pooled.effective, TIER_ARCHETYPE_AGNOSTIC)
        return (REPUTATION_PRIOR, TIER_PRIOR)

    def _load_sync(self, identity: str, kind: str, regime: str) -> sqlite3.Row | None:
        conn = self._connect()
        try:
            col = _id_column(kind)
            # table/col come from a validated whitelist, never user input.
            sql = f"SELECT reputation, sample_count FROM {_table(kind)} WHERE {col} = ? AND regime = ?"  # noqa: S608
            return conn.execute(sql, (identity, regime)).fetchone()
        finally:
            conn.close()

    async def set_reputation(
        self, identity: str, kind: str, reputation: float, sample_count: int, *,
        regime: str = "", updated_at: str,
    ) -> None:
        """Low-level upsert of a clamped reputation value.

        This is persistence only. Piece 2 layers the bounded EMA update rule on
        top of this primitive; nothing in the resolution path calls it yet.
        """
        async with self._lock:
            await asyncio.to_thread(
                self._upsert_sync, identity, kind, _clamp(reputation),
                max(0, sample_count), regime, updated_at,
            )

    def _upsert_sync(self, identity: str, kind: str, reputation: float,
                     sample_count: int, regime: str, updated_at: str) -> None:
        conn = self._connect()
        try:
            self._write_cell(conn, identity, kind, reputation, sample_count, regime, updated_at)
            conn.commit()
        finally:
            conn.close()

    async def apply_step(
        self, *, prediction_id: str, identity: str, kind: str, target: float,
        weight: float, outcome: str, stage: str, regime: str = "", updated_at: str,
    ) -> str:
        """Apply one bounded EMA step toward `target`, idempotent per prediction.

        EMA: new = clamp(old + weight*(target - old)); an unseen cell starts at
        the prior. Returns the action taken: "applied", "superseded", or "skipped".

        Supersede (Decision: 7-day authoritative replaces 24h provisional):
          - a prediction that already contributed at the same/higher stage is a
            no-op (idempotent — protects against re-runs and double-hooks).
          - an authoritative label over a prior provisional one BACKS OUT the
            provisional delta, then applies the authoritative step WITHOUT a second
            sample — one prediction, one sample, never two stacked steps.
        """
        async with self._lock:
            return await asyncio.to_thread(
                self._apply_step_sync, prediction_id, identity, kind, target,
                weight, outcome, stage, regime, updated_at,
            )

    def _apply_step_sync(self, prediction_id: str, identity: str, kind: str,
                         target: float, weight: float, outcome: str, stage: str,
                         regime: str, updated_at: str) -> str:
        conn = self._connect()
        try:
            prior = conn.execute(
                "SELECT applied_delta, stage FROM reputation_contribution "
                "WHERE prediction_id=? AND identity=? AND kind=? AND regime=?",
                (prediction_id, identity, kind, regime),
            ).fetchone()

            # idempotency: same prediction already final, or re-run of same stage.
            if prior is not None and (
                prior["stage"] == STAGE_AUTHORITATIVE or prior["stage"] == stage
            ):
                conn.commit()
                return "skipped"

            rep, count = self._read_cell(conn, identity, kind, regime)
            action = "applied"
            if prior is not None:
                # supersede: back out the provisional delta, reapply, same sample.
                rep = _clamp(rep - float(prior["applied_delta"]))
                action = "superseded"
            else:
                count += 1  # new prediction → one sample.

            old = rep
            new = _clamp(old + weight * (target - old))
            self._write_cell(conn, identity, kind, new, count, regime, updated_at)
            conn.execute(
                "INSERT INTO reputation_contribution "
                "(prediction_id, identity, kind, regime, applied_delta, stage, outcome, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(prediction_id, identity, kind, regime) DO UPDATE SET "
                "applied_delta=excluded.applied_delta, stage=excluded.stage, "
                "outcome=excluded.outcome, updated_at=excluded.updated_at",
                (prediction_id, identity, kind, regime, new - old, stage, outcome, updated_at),
            )
            conn.commit()
            return action
        finally:
            conn.close()

    def _read_cell(self, conn, identity: str, kind: str, regime: str) -> tuple[float, int]:
        col = _id_column(kind)
        sql = f"SELECT reputation, sample_count FROM {_table(kind)} WHERE {col}=? AND regime=?"  # noqa: S608
        row = conn.execute(sql, (identity, regime)).fetchone()
        if row is None:
            return REPUTATION_PRIOR, 0  # unseen cell starts EMA at the prior.
        return float(row["reputation"]), int(row["sample_count"])

    def _write_cell(self, conn, identity: str, kind: str, reputation: float,
                    sample_count: int, regime: str, updated_at: str) -> None:
        col = _id_column(kind)
        # table/col come from a validated whitelist, never user input.
        sql = f"INSERT INTO {_table(kind)} ({col}, regime, reputation, sample_count, updated_at) VALUES (?,?,?,?,?) ON CONFLICT({col}, regime) DO UPDATE SET reputation=excluded.reputation, sample_count=excluded.sample_count, updated_at=excluded.updated_at"  # noqa: S608
        conn.execute(sql, (identity, regime, _clamp(reputation), max(0, sample_count), updated_at))
