#!/usr/bin/env python3
"""Standalone reconstruction of backtest metrics from raw backtest_predictions rows.

Independence rule: imports NOTHING from backend/ — formulas are deliberately
duplicated from the spec (annualised Sharpe over 252 days, peak-to-trough
drawdown, deadband-excluded hit rate). If the backend drifts, this diverges
and the divergence is the alarm.

Usage:
    python verify_backtest.py --db ../aussieintel.db --run-id bt_abc123 \
        [--endpoint https://host/api/backtest/results/bt_abc123 | --json response.json]

Exit 0 on match within 1e-6 relative; exit 1 with field-level diff.
"""

import argparse
import json
import math
import sqlite3
import statistics
import sys
import urllib.request

REL_TOL = 1e-6
BANDS = {"0-25%": (0.00, 0.25), "25-50%": (0.25, 0.50),
         "50-75%": (0.50, 0.75), "75-100%": (0.75, 1.01)}


def load_rows(db_path: str, run_id: str) -> list[dict]:
    # insertion order = generation order
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT direction, confidence, entry_price, change_pct, outcome "
        "FROM backtest_predictions WHERE run_id = ? ORDER BY id", (run_id,))]
    con.close()
    return rows


def compute_sharpe(returns: list[float]) -> float:
    # annualised sharpe, 252 days
    if len(returns) < 2:
        return 0.0
    std = statistics.stdev(returns)
    return round(statistics.mean(returns) / std * math.sqrt(252), 3) if std else 0.0


def compute_max_drawdown(returns: list[float]) -> float:
    # peak-to-trough on cumulative equity
    cum = peak = 1.0
    worst = 0.0
    for r in returns:
        cum *= 1.0 + r
        peak = max(peak, cum)
        worst = max(worst, (peak - cum) / peak)
    return round(worst, 4)


def reconstruct(rows: list[dict]) -> dict:
    # neutral direction excluded from stats
    directional = [r for r in rows if r["direction"] != "NEUTRAL"]
    total = len(directional)
    correct = sum(1 for r in directional if r["outcome"] == "CORRECT")
    incorrect = sum(1 for r in directional if r["outcome"] == "INCORRECT")
    neutral = sum(1 for r in rows if r["outcome"] == "NEUTRAL")

    by_conf: dict = {}
    for label, (lo, hi) in BANDS.items():
        band = [r for r in directional if lo <= r["confidence"] < hi]
        ok = sum(1 for r in band if r["outcome"] == "CORRECT")
        by_conf[label] = {"total": len(band), "correct": ok,
                          "hit_rate": round(ok / len(band), 3) if band else 0.0}

    # long when up, short when down
    returns = [(r["change_pct"] / 100.0) * (1.0 if r["direction"] == "UP" else -1.0)
               for r in directional if r["entry_price"] and r["entry_price"] > 0]
    gains = sum(x for x in returns if x > 0)
    losses = sum(-x for x in returns if x < 0)

    return {
        "total_predictions": total, "correct": correct, "incorrect": incorrect,
        "neutral": neutral,
        "hit_rate": round(correct / total, 3) if total else 0.0,
        "hit_rate_by_confidence": by_conf,
        "sharpe_ratio": compute_sharpe(returns),
        "max_drawdown": compute_max_drawdown(returns),
        "profit_factor": round(gains / losses, 3) if losses > 0 else 0.0,
    }


def published_metrics(endpoint: str | None, json_path: str | None) -> dict | None:
    # accept envelope, data, or bare metrics
    if endpoint:
        with urllib.request.urlopen(endpoint, timeout=30) as resp:
            obj = json.load(resp)
    elif json_path:
        with open(json_path, encoding="utf-8") as fh:
            obj = json.load(fh)
    else:
        return None
    data = obj.get("data", obj) if isinstance(obj, dict) else {}
    return data.get("metrics", data)


def flatten(d: dict, prefix: str = "") -> dict:
    # dotted keys for nested diff
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def values_match(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=REL_TOL)
    return a == b


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="../aussieintel.db")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--endpoint", help="results endpoint url to compare against")
    ap.add_argument("--json", help="saved results response to compare against")
    args = ap.parse_args()

    rows = load_rows(args.db, args.run_id)
    if not rows:
        print(f"no backtest_predictions rows for run_id={args.run_id}")
        return 1
    recon = reconstruct(rows)

    published = published_metrics(args.endpoint, args.json)
    if published is None:
        # no comparison target — print reconstruction
        print(json.dumps(recon, indent=2))
        return 0

    want, got = flatten(recon), flatten(published)
    diffs = [f"  {k}: reconstructed={v} published={got.get(k, '<missing>')}"
             for k, v in want.items() if not values_match(v, got.get(k))]
    if diffs:
        print(f"MISMATCH run {args.run_id} — {len(diffs)} field(s) diverge:")
        print("\n".join(diffs))
        return 1
    print(f"MATCH run {args.run_id}: all {len(want)} fields within {REL_TOL} relative")
    return 0


if __name__ == "__main__":
    sys.exit(main())
