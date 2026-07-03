"""
Tests for the Stage 2b verify scripts.

verify_backtest.py  — run as a subprocess against a seeded isolated DB and a
                      captured results-response JSON; exit codes are the contract.
verify_duplicates.py — field-mapping/comparison functions unit-tested by
                       importing the script as a module with fixture JSON.
                       No network is ever touched.

The verify scripts import nothing from backend/; tests MAY import backend
code (engine DDL + metrics) to seed data and capture the endpoint shape.
"""

import importlib.util
import json
import math
import sqlite3
import statistics
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from backtesting.backtest_engine import (
    _BACKTEST_DDL,
    BacktestPrediction,
    calculate_metrics,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERIFY_BACKTEST = BACKEND_DIR / "scripts" / "verify" / "verify_backtest.py"
VERIFY_DUPLICATES = BACKEND_DIR / "scripts" / "verify" / "verify_duplicates.py"

RUN_ID = "bt_verify_test01"

# (date, ticker, direction, confidence, entry, exit, change_pct, outcome)
# outcomes follow the 0.5% deadband rule; one neutral direction, two neutral outcomes
SEED_ROWS = [
    ("2025-01-06", "BHP.AX", "UP",      0.60, 100.0, 101.20,  1.2, "CORRECT"),
    ("2025-01-07", "BHP.AX", "UP",      0.55,  50.0,  49.50, -1.0, "INCORRECT"),
    ("2025-01-08", "BHP.AX", "DOWN",    0.70,  40.0,  39.20, -2.0, "CORRECT"),
    ("2025-01-09", "BHP.AX", "DOWN",    0.45,  20.0,  20.30,  1.5, "INCORRECT"),
    ("2025-01-10", "BHP.AX", "UP",      0.40,  30.0,  30.03,  0.1, "NEUTRAL"),
    ("2025-01-13", "BHP.AX", "NEUTRAL", 0.30,  10.0,  10.50,  5.0, "NEUTRAL"),
    ("2025-01-14", "BHP.AX", "UP",      0.75, 200.0, 206.00,  3.0, "CORRECT"),
    ("2025-01-15", "BHP.AX", "DOWN",    0.65,  80.0,  82.40,  3.0, "INCORRECT"),
    ("2025-01-16", "BHP.AX", "UP",      0.50,  60.0,  61.20,  2.0, "CORRECT"),
    ("2025-01-17", "BHP.AX", "DOWN",    0.35,  90.0,  88.20, -2.0, "CORRECT"),
]

# signed daily returns: long when UP, short when DOWN, NEUTRAL direction excluded
EXPECTED_RETURNS = [0.012, -0.010, 0.020, -0.015, 0.001, 0.030, -0.030, 0.020, 0.020]


def _predictions() -> list[BacktestPrediction]:
    return [
        BacktestPrediction(
            date=d, ticker=t, direction=dr, confidence=c,
            entry_price=en, exit_price=ex, change_pct=ch, outcome=o,
        )
        for d, t, dr, c, en, ex, ch, o in SEED_ROWS
    ]


def _hand_sharpe(returns: list[float]) -> float:
    """Annualised Sharpe computed independently: mean/stdev * sqrt(252)."""
    return round(statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252), 3)


def _hand_max_drawdown(returns: list[float]) -> float:
    """Peak-to-trough drawdown computed independently."""
    cum, peak, worst = 1.0, 1.0, 0.0
    for r in returns:
        cum *= 1.0 + r
        peak = max(peak, cum)
        worst = max(worst, (peak - cum) / peak)
    return round(worst, 4)


@pytest.fixture
def seeded_db(tmp_path) -> tuple[Path, dict]:
    """Isolated DB with one completed run and 10 backtest_predictions rows."""
    db_path = tmp_path / "verify_test.db"
    metrics = asdict(calculate_metrics(_predictions()))

    con = sqlite3.connect(db_path)
    con.executescript(_BACKTEST_DDL)
    con.execute(
        """INSERT INTO backtest_runs
           (run_id, config, status, started_at, completed_at, metrics, progress, total_steps)
           VALUES (?, ?, 'completed', '2025-02-01T00:00:00+00:00',
                   '2025-02-01T00:05:00+00:00', ?, 10, 10)""",
        (RUN_ID, json.dumps({"tickers": ["BHP.AX"], "start_date": "2025-01-06",
                             "end_date": "2025-01-17", "lookback_days": 30}),
         json.dumps(metrics)),
    )
    con.executemany(
        """INSERT INTO backtest_predictions
           (run_id, prediction_date, ticker, direction, confidence,
            entry_price, exit_price, change_pct, outcome)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(RUN_ID, d, t, dr, c, en, ex, ch, o) for d, t, dr, c, en, ex, ch, o in SEED_ROWS],
    )
    con.commit()
    con.close()
    return db_path, metrics


def _response_json(metrics: dict) -> dict:
    """Shape of GET /api/backtest/results/{run_id} for a completed run."""
    return {
        "status": "success",
        "data": {"run_id": RUN_ID, "status": "completed", "metrics": metrics,
                 "predictions": [], "pagination": {}},
    }


def _run_verify(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFY_BACKTEST), *args],
        capture_output=True, text=True, timeout=60,
    )


# ── verify_backtest.py ─────────────────────────────────────────────────────────

def test_engine_metrics_match_hand_computed_values():
    """Triangulation: engine Sharpe/drawdown equal an independent hand computation."""
    metrics = calculate_metrics(_predictions())
    assert metrics.sharpe_ratio == _hand_sharpe(EXPECTED_RETURNS)
    assert metrics.max_drawdown == _hand_max_drawdown(EXPECTED_RETURNS)
    assert metrics.total_predictions == 9      # NEUTRAL direction excluded
    assert metrics.correct == 5
    assert metrics.incorrect == 3
    assert metrics.neutral == 2                # neutral outcomes counted separately
    assert metrics.hit_rate == round(5 / 9, 3)
    assert metrics.profit_factor == round(0.103 / 0.055, 3)


def test_verify_backtest_matches_endpoint_response_exit_0(seeded_db, tmp_path):
    db_path, metrics = seeded_db
    json_path = tmp_path / "response.json"
    json_path.write_text(json.dumps(_response_json(metrics)), encoding="utf-8")

    result = _run_verify("--db", str(db_path), "--run-id", RUN_ID, "--json", str(json_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_verify_backtest_detects_corrupted_value_exit_1(seeded_db, tmp_path):
    db_path, metrics = seeded_db
    corrupted = {**metrics, "sharpe_ratio": metrics["sharpe_ratio"] + 0.5}
    json_path = tmp_path / "corrupted.json"
    json_path.write_text(json.dumps(_response_json(corrupted)), encoding="utf-8")

    result = _run_verify("--db", str(db_path), "--run-id", RUN_ID, "--json", str(json_path))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "MISMATCH" in result.stdout
    assert "sharpe_ratio" in result.stdout


def test_verify_backtest_prints_reconstruction_without_target(seeded_db):
    db_path, metrics = seeded_db
    result = _run_verify("--db", str(db_path), "--run-id", RUN_ID)
    assert result.returncode == 0, result.stdout + result.stderr
    recon = json.loads(result.stdout)
    assert recon["hit_rate"] == metrics["hit_rate"]
    assert recon["sharpe_ratio"] == metrics["sharpe_ratio"]
    assert recon["max_drawdown"] == metrics["max_drawdown"]


def test_verify_backtest_unknown_run_id_exit_1(seeded_db):
    db_path, _ = seeded_db
    result = _run_verify("--db", str(db_path), "--run-id", "bt_does_not_exist")
    assert result.returncode == 1
    assert "no backtest_predictions rows" in result.stdout


# ── verify_duplicates.py (module import, no network) ──────────────────────────

@pytest.fixture(scope="module")
def dup():
    spec = importlib.util.spec_from_file_location("verify_duplicates", VERIFY_DUPLICATES)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _accuracy_payloads(correct_summary: int = 22) -> dict:
    """Fixture payloads in each endpoint's real response shape."""
    return {
        "/api/predict/accuracy": {
            "status": "success",
            "data": {"total": 40, "correct": 22, "accuracy_pct": 55.0, "breakdown": {}},
        },
        "/api/predictions/accuracy": {
            "status": "success",
            "data": {"total_predictions": 50, "resolved_predictions": 40,
                     "correct_predictions": 22, "direction_accuracy_pct": 55.0},
        },
        "/api/accuracy/summary": {
            "scope": "overall", "total_predictions": 50, "resolved_predictions": 40,
            "correct": correct_summary,
            "accuracy_pct": round(correct_summary / 40 * 100, 2),
        },
    }


def test_compare_values_agree_within_pct_tolerance(dup):
    values = {"a": 55.0, "b": 55.04}  # cross-endpoint rounding difference
    assert dup.compare_values(values, tol=dup.PCT_TOL) == "AGREE"


def test_compare_values_diverge_on_count_mismatch(dup):
    assert dup.compare_values({"a": 40, "b": 41}, tol=dup.COUNT_TOL) == "DIVERGE"


def test_compare_values_not_comparable_with_single_value(dup):
    assert dup.compare_values({"a": 40, "b": None}) == "NOT-COMPARABLE"


def test_accuracy_cluster_agrees_on_mapped_fields(dup):
    fields = dup.accuracy_fields(_accuracy_payloads())
    verdicts = {f["field"]: f["verdict"] for f in fields}
    assert verdicts == {"resolved_count": "AGREE", "correct_count": "AGREE",
                        "accuracy_pct": "AGREE"}


def test_accuracy_cluster_detects_divergent_correct_count(dup):
    fields = dup.accuracy_fields(_accuracy_payloads(correct_summary=21))
    verdicts = {f["field"]: f["verdict"] for f in fields}
    assert verdicts["correct_count"] == "DIVERGE"
    assert verdicts["accuracy_pct"] == "DIVERGE"  # 52.5 vs 55.0 exceeds tolerance


def test_accuracy_cluster_unreachable_member_drops_out(dup):
    payloads = _accuracy_payloads()
    payloads["/api/accuracy/summary"] = None  # simulated fetch failure
    fields = dup.accuracy_fields(payloads)
    # remaining two members still comparable
    assert all(f["verdict"] == "AGREE" for f in fields)


def test_calibration_cluster_maps_sample_size_and_flags_bins(dup):
    payloads = {
        "/api/predictions/calibration": {"status": "success", "data": {"sample_size": 120}},
        "/api/accuracy/calibration": {"status": "success", "data": {"n": 120, "brier_score": 0.21}},
    }
    fields = {f["field"]: f["verdict"] for f in dup.calibration_fields(payloads)}
    assert fields["resolved_sample_size"] == "AGREE"
    assert fields["reliability_bins"] == "NOT-COMPARABLE"


def test_history_cluster_detects_ticker_divergence(dup):
    payloads = {
        dup.HISTORY_EPS[0]: {"status": "success", "count": 2,
                             "data": [{"ticker": "BHP.AX"}, {"ticker": "RIO.AX"}]},
        dup.HISTORY_EPS[1]: {"status": "success", "count": 2,
                             "data": [{"ticker": "BHP.AX"}, {"ticker": "CBA.AX"}]},
    }
    fields = {f["field"]: f["verdict"] for f in dup.history_fields(payloads)}
    assert fields["row_count"] == "AGREE"
    assert fields["distinct_tickers"] == "DIVERGE"


def test_backtest_cluster_is_explicitly_not_comparable(dup):
    payloads = {
        dup.BACKTEST_EPS[0]: {"status": "success", "data": {"sample_size": 12}},
        dup.BACKTEST_EPS[1]: {"status": "success",
                              "data": [{"status": "completed"}, {"status": "failed"}]},
    }
    fields = dup.backtest_fields(payloads)
    assert all(f["verdict"] == "NOT-COMPARABLE" for f in fields)
    completed = next(f for f in fields if f["field"].startswith("completed_run_count"))
    assert completed["values"][dup.BACKTEST_EPS[1]] == 1


def _cluster(verdict: str, fields=None, endpoints=None, errors=None) -> dict:
    return {"cluster": "x", "endpoints": endpoints or ["/a", "/b"],
            "errors": errors or {}, "fields": fields or [], "verdict": verdict}


def test_exit_code_2_on_any_divergence(dup):
    clusters = [_cluster("AGREE"), _cluster("DIVERGE")]
    assert dup.exit_code(clusters) == 2


def test_exit_code_0_when_all_agree_or_not_comparable(dup):
    clusters = [_cluster("AGREE"), _cluster("NOT-COMPARABLE")]
    assert dup.exit_code(clusters) == 0


def test_exit_code_1_when_every_endpoint_unreachable(dup):
    errors = {"/a": "URLError: refused", "/b": "URLError: refused"}
    clusters = [_cluster("UNREACHABLE", errors=errors)]
    assert dup.exit_code(clusters) == 1


def test_render_report_contains_cluster_verdicts_and_values(dup):
    fields = dup.accuracy_fields(_accuracy_payloads(correct_summary=21))
    cluster = {"cluster": "accuracy", "endpoints": dup.ACCURACY_EPS, "errors": {},
               "fields": fields, "verdict": dup.cluster_verdict(fields, {})}
    report = dup.render_report([cluster], "https://staging.example", "testtag")
    assert "DIVERGE" in report
    assert "ANDON" in report
    assert "/api/accuracy/summary" in report
    assert "testtag" in report
