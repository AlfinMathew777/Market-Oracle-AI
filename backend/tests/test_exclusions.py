"""A1 — enumerated exclusion codes and the append-only exclusion guard.

Exclusion semantics under test:
  - _is_garbage_prediction returns enumerated codes, never free text
  - mark_excluded() is append-only: sets exclusion, refuses to clear or
    rewrite one, rejects non-enumerated codes, and logs every call at INFO
  - save_prediction_log's INSERT OR REPLACE can never zero out an
    existing exclusion (the only code path that previously could)
"""

import logging

import aiosqlite
import pytest

from validation.exclusions import (
    EXCLUSION_CODES,
    GARBAGE_CONFIDENCE_SUBFLOOR,
    GARBAGE_CONFIDENCE_ZERO,
)

pytestmark = pytest.mark.unit


async def _insert_row(db_path: str, pred_id: str, confidence: float = 0.7,
                      excluded: int = 0, reason=None) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO prediction_log
               (id, ticker, predicted_direction, confidence, predicted_at,
                excluded_from_stats, exclusion_reason, created_at)
               VALUES (?, 'BHP.AX', 'bullish', ?, '2026-06-01T00:00:00+00:00',
                       ?, ?, '2026-06-01T00:00:00+00:00')""",
            (pred_id, confidence, excluded, reason),
        )
        await db.commit()


async def _fetch_exclusion(db_path: str, pred_id: str) -> tuple:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT excluded_from_stats, exclusion_reason FROM prediction_log WHERE id = ?",
            (pred_id,),
        ) as cur:
            return await cur.fetchone()


class TestGarbageDetectionCodes:
    def test_zero_confidence_returns_zero_code(self):
        from database import _is_garbage_prediction
        assert _is_garbage_prediction("neutral", 0.0) == GARBAGE_CONFIDENCE_ZERO

    def test_subfloor_confidence_returns_subfloor_code(self):
        from database import _is_garbage_prediction
        assert _is_garbage_prediction("bullish", 0.03) == GARBAGE_CONFIDENCE_SUBFLOOR

    def test_normal_confidence_returns_none(self):
        from database import _is_garbage_prediction
        assert _is_garbage_prediction("bullish", 0.55) is None

    def test_all_writers_use_enumerated_codes_only(self):
        # both possible writer outputs are members of the enum
        from database import _is_garbage_prediction
        for conf in (0.0, 0.01, 0.049):
            assert _is_garbage_prediction("bullish", conf) in EXCLUSION_CODES


class TestMarkExcludedAppendOnly:
    async def test_marks_row_with_code(self, isolated_db, caplog):
        from database import mark_excluded
        await _insert_row(isolated_db, "p1")

        with caplog.at_level(logging.INFO, logger="database"):
            assert await mark_excluded("p1", GARBAGE_CONFIDENCE_ZERO) is True

        assert await _fetch_exclusion(isolated_db, "p1") == (1, GARBAGE_CONFIDENCE_ZERO)
        assert any("p1" in r.message and GARBAGE_CONFIDENCE_ZERO in r.message
                   for r in caplog.records)

    async def test_refuses_to_clear_and_logs(self, isolated_db, caplog):
        """No un-exclude path: a falsy/None code is refused with the row untouched."""
        from database import mark_excluded
        await _insert_row(isolated_db, "p2", excluded=1, reason=GARBAGE_CONFIDENCE_ZERO)

        with caplog.at_level(logging.INFO, logger="database"):
            with pytest.raises(ValueError):
                await mark_excluded("p2", None)
            with pytest.raises(ValueError):
                await mark_excluded("p2", "")

        assert await _fetch_exclusion(isolated_db, "p2") == (1, GARBAGE_CONFIDENCE_ZERO)
        assert any("REFUSED" in r.message for r in caplog.records)

    async def test_rejects_free_text_reason(self, isolated_db):
        from database import mark_excluded
        await _insert_row(isolated_db, "p3")
        with pytest.raises(ValueError):
            await mark_excluded("p3", "manually removed by admin")
        assert await _fetch_exclusion(isolated_db, "p3") == (0, None)

    async def test_existing_exclusion_never_rewritten(self, isolated_db, caplog):
        from database import mark_excluded
        await _insert_row(isolated_db, "p4", excluded=1, reason=GARBAGE_CONFIDENCE_ZERO)

        with caplog.at_level(logging.INFO, logger="database"):
            assert await mark_excluded("p4", GARBAGE_CONFIDENCE_SUBFLOOR) is False

        # first exclusion wins — append-only
        assert await _fetch_exclusion(isolated_db, "p4") == (1, GARBAGE_CONFIDENCE_ZERO)

    async def test_unknown_prediction_returns_false(self, isolated_db):
        from database import mark_excluded
        assert await mark_excluded("nope", GARBAGE_CONFIDENCE_ZERO) is False


class TestSaveReplacePreservesExclusion:
    async def test_replace_cannot_zero_out_exclusion(self, isolated_db):
        """INSERT OR REPLACE was the one path that could clear an exclusion."""
        from database import save_prediction_log

        # first save: garbage → excluded at write time
        await save_prediction_log("sim-x", "BHP.AX", "NEUTRAL", 0.0, "no signal", {})
        assert await _fetch_exclusion(isolated_db, "sim-x") == (1, GARBAGE_CONFIDENCE_ZERO)

        # replay with healthy confidence must NOT un-exclude
        await save_prediction_log("sim-x", "BHP.AX", "UP", 0.70, "retry", {})
        assert await _fetch_exclusion(isolated_db, "sim-x") == (1, GARBAGE_CONFIDENCE_ZERO)

    async def test_fresh_healthy_row_not_excluded(self, isolated_db):
        from database import save_prediction_log
        await save_prediction_log("sim-y", "BHP.AX", "UP", 0.70, "signal", {})
        assert await _fetch_exclusion(isolated_db, "sim-y") == (0, None)


class TestLegacyReasonNormalization:
    async def test_backfill_writes_codes_and_normalizes_free_text(self, isolated_db):
        from database import mark_existing_garbage_predictions

        # legacy free-text reason on an already-excluded row
        await _insert_row(isolated_db, "legacy1", confidence=0.0, excluded=1,
                          reason="Zero confidence — no signal (minimum confidence guard triggered)")
        await _insert_row(isolated_db, "legacy2", confidence=0.02, excluded=1,
                          reason="Confidence 2.0% below minimum 5% threshold")
        # unmarked garbage row the backfill must catch with a code
        await _insert_row(isolated_db, "fresh1", confidence=0.0)

        n = await mark_existing_garbage_predictions()
        assert n == 1  # only fresh1 newly marked

        assert await _fetch_exclusion(isolated_db, "legacy1") == (1, GARBAGE_CONFIDENCE_ZERO)
        assert await _fetch_exclusion(isolated_db, "legacy2") == (1, GARBAGE_CONFIDENCE_SUBFLOOR)
        assert await _fetch_exclusion(isolated_db, "fresh1") == (1, GARBAGE_CONFIDENCE_ZERO)
