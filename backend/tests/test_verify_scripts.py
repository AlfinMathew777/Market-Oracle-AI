"""
Integration tests — scripts/verify reconstruction scripts (Stage 2b).

Direction of authority: endpoints are validated AGAINST the verify scripts,
never vice versa. Each test seeds an isolated DB with hand-built rows,
captures the endpoint output in-process (direct trust/service calls — this
side may import backend), then runs the verify script as a SUBPROCESS with
--db and --json and requires exit 0. The scripts themselves import nothing
from backend/ — their formulas are deliberate duplicates.

Seed coverage: correct/incorrect outcomes, deadband-boundary +/-0.5 moves,
neutral predictions, legacy tokens (up/down/flat), an unvalidatable token,
both horizons (24h driver vs 7-day), excluded rows, unresolved rows, and
deliberately WRONG prediction_correct flags (track record must re-derive).
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERIFY_DIR = BACKEND_DIR / "scripts" / "verify"

_NOW = datetime.now(timezone.utc)
_RESOLVED_AT = (_NOW - timedelta(days=2)).isoformat()
_PREDICTED_AT = (_NOW - timedelta(days=3)).isoformat()
_DRIVER_24H = "Auto-validated via 24h price action"
_DRIVER_7D = "7-day authoritative resolution"

# (id, direction, confidence, change_pct, driver, prediction_correct,
#  resolved, excluded) — prediction_correct is deliberately wrong on r02.
_PREDICTION_LOG_ROWS = [
    # 24h horizon
    ("r01", "bullish", 0.72, 2.00, _DRIVER_24H, 1, True, 0),    # CORRECT
    ("r02", "bullish", 0.65, -1.50, _DRIVER_24H, 1, True, 0),   # INCORRECT (flag lies)
    ("r03", "bearish", 0.80, -3.00, _DRIVER_24H, 1, True, 0),   # CORRECT
    ("r04", "bearish", 0.58, 1.20, _DRIVER_24H, 0, True, 0),    # INCORRECT
    ("r05", "bullish", 0.60, 0.30, _DRIVER_24H, None, True, 0),  # in deadband
    ("r06", "bullish", 0.70, 0.50, _DRIVER_24H, None, True, 0),  # boundary: neutral
    ("r07", "bullish", 0.62, -0.51, _DRIVER_24H, 0, True, 0),   # just clears band
    ("r08", "neutral", 0.40, 1.00, _DRIVER_24H, None, True, 0),  # neutral prediction
    ("r09", "bullish", 0.72, 1.10, _DRIVER_24H, 1, True, 0),    # CORRECT, dup conf
    # 7-day horizon
    ("r10", "up", 0.77, 1.80, _DRIVER_7D, 1, True, 0),          # legacy bullish token
    ("r11", "down", 0.66, 2.50, _DRIVER_7D, 0, True, 0),        # legacy bearish, wrong
    ("r12", "bearish", 0.55, -0.50, _DRIVER_7D, None, True, 0),  # boundary: neutral
    ("r13", "sideways_drift", 0.50, 1.00, _DRIVER_7D, 0, True, 0),  # unvalidatable
    ("r14", "flat", 0.35, -0.20, _DRIVER_7D, 0, True, 0),       # legacy neutral token
    ("r15", "bullish", 0.90, 4.00, _DRIVER_7D, 1, True, 0),     # CORRECT, top bucket
    ("r16", "bearish", 0.45, -2.00, _DRIVER_7D, 1, True, 0),    # CORRECT, low bucket
    ("r17", "bullish", 0.68, -2.20, _DRIVER_7D, 0, True, 0),    # INCORRECT
    # rows no metric family may count
    ("r18", "bullish", 0.75, None, None, None, False, 1),       # excluded, pending
    ("r19", "bearish", 0.80, None, None, None, False, 1),       # excluded, pending
    ("r20", "bullish", 0.70, None, None, None, False, 0),       # unresolved
    ("r21", "bullish", 0.70, None, None, None, True, 0),        # resolved, no change pct
]

# (id, status, return_pct, confidence_score 0-100)
_REASONING_ROWS = [
    ("rp1", "CORRECT", 3.2, 78),
    ("rp2", "INCORRECT", -2.5, 64),
    ("rp3", "PARTIAL", 1.0, 71),
    ("rp4", "STOPPED_OUT", -4.0, 82),
    ("rp5", "PENDING", None, 60),
    ("rp6", "EXPIRED", 0.4, 55),
]


async def _seed(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        for pid, direction, conf, change, driver, correct, resolved, excluded in _PREDICTION_LOG_ROWS:
            await db.execute(
                """INSERT INTO prediction_log
                   (id, ticker, predicted_direction, confidence, predicted_at,
                    bhp_price_at_prediction, actual_price_change_pct,
                    prediction_correct, actual_driver, resolved_at,
                    excluded_from_stats, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, "BHP.AX", direction, conf, _PREDICTED_AT, 45.20, change,
                 correct, driver, _RESOLVED_AT if resolved else None,
                 excluded, _PREDICTED_AT),
            )
        ts = (_NOW - timedelta(days=5)).isoformat()
        for rid, status, ret, conf_score in _REASONING_ROWS:
            await db.execute(
                """INSERT INTO reasoning_predictions
                   (id, stock_ticker, prediction_timestamp, direction,
                    recommendation, confidence_score, price_at_prediction,
                    outcome_status, actual_return_pct, reasoning_output)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, "BHP.AX", ts, "Bullish", "BUY", conf_score, 45.20,
                 status, ret, "{}"),
            )
        await db.commit()


@pytest_asyncio.fixture
async def seeded_db(isolated_db):
    await _seed(isolated_db)
    return isolated_db


def _run_script(name: str, db_path: str, json_path=None, extra=()):
    cmd = [sys.executable, str(VERIFY_DIR / name), "--db", str(db_path), *extra]
    if json_path is not None:
        cmd += ["--json", str(json_path)]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )


def _capture(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestVerifyScriptsMatchEndpoints:
    """Happy path: subprocess reconstruction agrees with the live handler."""

    async def test_track_record_matches_reconstruction(self, seeded_db, tmp_path):
        from trust.track_record import get_track_record

        payload = await get_track_record()
        assert "error" not in payload
        # pin the seed: 6 directional resolved on 24h, 5 on 7d
        assert payload["provisional_24h"]["n_resolved_directional"] == 6
        assert payload["authoritative_7d"]["n_resolved_directional"] == 5
        assert payload["provisional_24h"]["n_excluded_neutral"] == 3

        json_path = _capture(tmp_path, "track_record.json", payload)
        result = _run_script("verify_track_record.py", seeded_db, json_path)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    async def test_calibration_matches_reconstruction(self, seeded_db, tmp_path):
        from trust.track_record import get_calibration

        data = await get_calibration()
        assert "error" not in data
        assert data["n"] == 17          # every resolved row, both horizons
        assert data["n_scored"] == 16   # unvalidatable token skipped

        json_path = _capture(tmp_path, "calibration.json",
                             {"status": "success", "data": data})
        result = _run_script("verify_calibration.py", seeded_db, json_path)
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    async def test_accuracy_summary_matches_reconstruction(self, seeded_db, tmp_path):
        from database import get_reasoning_accuracy_stats

        payload = await get_reasoning_accuracy_stats(days=90)
        assert "error" not in payload
        assert payload["resolved_predictions"] == 5
        assert payload["correct"] == 1

        json_path = _capture(tmp_path, "accuracy_summary.json", payload)
        result = _run_script("verify_accuracy_summary.py", seeded_db, json_path,
                             extra=("--days", "90"))
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    async def test_validation_summary_matches_reconstruction(self, seeded_db, tmp_path):
        from validation.outcome_checker import get_validation_summary

        payload = await get_validation_summary(days=30)
        assert "error" not in payload
        # this family trusts stored prediction_correct — 13 rows carry a flag
        assert payload["total_validated"] == 13
        assert payload["correct"] == 7  # includes r02's lying flag — this family trusts it
        assert payload["unvalidatable_count"] == 1

        json_path = _capture(tmp_path, "validation_summary.json", payload)
        result = _run_script("verify_validation_summary.py", seeded_db, json_path,
                             extra=("--days", "30"))
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


class TestVerifyScriptContract:
    """Exit-code contract: named diff on mismatch, plain dump without compare."""

    async def test_corrupted_field_exits_1_and_names_it(self, seeded_db, tmp_path):
        from trust.track_record import get_track_record

        payload = await get_track_record()
        payload["authoritative_7d"]["hit_rate"] = 0.9999  # a lie the script must catch

        json_path = _capture(tmp_path, "corrupted.json", payload)
        result = _run_script("verify_track_record.py", seeded_db, json_path)
        assert result.returncode == 1, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert "authoritative_7d.hit_rate" in result.stdout

    async def test_reconstruction_only_mode_prints_json(self, seeded_db):
        result = _run_script("verify_track_record.py", seeded_db)
        assert result.returncode == 0, result.stderr
        recon = json.loads(result.stdout)
        assert recon["provisional_24h"]["n_resolved_directional"] == 6
        assert recon["deadband_pct"] == 0.5
