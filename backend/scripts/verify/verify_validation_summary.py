#!/usr/bin/env python3
"""recompute GET /api/metrics/validation-summary from raw prediction_log rows.

published semantics duplicated exactly — including where they differ from the
track record family: the stored prediction_correct flag IS what this metric
publishes (no label re-derivation), only the literal lowercase 'neutral' token
is dropped from totals, and the window is resolved_at >= utc now - days.
bands: 55-65 / 65-75 / 75-85 / 85%+ (lower-closed, upper-open, top cap 1.01).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from _lib import (
    BEARISH_TOKENS, BULLISH_TOKENS, NEUTRAL_TOKENS,
    finish, make_parser, normalize_direction, query,
)

BANDS = (("55-65%", 0.55, 0.65), ("65-75%", 0.65, 0.75),
         ("75-85%", 0.75, 0.85), ("85%+", 0.85, 1.01))
KNOWN_TOKENS = BULLISH_TOKENS | BEARISH_TOKENS | NEUTRAL_TOKENS

_SQL = ("SELECT predicted_direction, confidence, prediction_correct{excl} "
        "FROM prediction_log WHERE prediction_correct IS NOT NULL "
        "AND resolved_at >= ? ORDER BY rowid")


def build(db_path: str, days: int) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        rows = query(db_path, _SQL.format(excl=", excluded_from_stats"), (since,))
    except sqlite3.OperationalError:
        # pre-migration db without the column
        rows = query(db_path, _SQL.format(excl=", 0 AS excluded_from_stats"), (since,))

    kept = [r for r in rows if not r["excluded_from_stats"]]
    excluded_count = sum(1 for r in rows if r["excluded_from_stats"] == 1)
    unvalidatable_count = sum(
        1 for r in kept if (r["predicted_direction"] or "").lower() not in KNOWN_TOKENS)

    # literal token only — legacy neutral aliases ('flat', 'hold', ...) pass through
    base = [r for r in kept if r["predicted_direction"] != "neutral"]
    total = len(base)
    correct = sum(int(r["prediction_correct"]) for r in base)

    by_direction: dict[str, dict] = {}
    for r in base:
        norm = normalize_direction(r["predicted_direction"])
        key = {"bullish": "BUY", "bearish": "SELL"}.get(norm, r["predicted_direction"].upper())
        slot = by_direction.setdefault(key, {"total": 0, "correct": 0})
        slot["total"] += 1
        slot["correct"] += int(r["prediction_correct"])
    for slot in by_direction.values():
        slot["hit_rate"] = round(slot["correct"] / slot["total"], 3)

    by_band: dict[str, dict] = {}
    for label, lo, hi in BANDS:
        band = [r for r in base if r["confidence"] is not None and lo <= r["confidence"] < hi]
        hits = sum(int(r["prediction_correct"]) for r in band)
        by_band[label] = {"total": len(band),
                          "hit_rate": round(hits / len(band), 3) if band else 0.0}

    return {
        "period_days": days,
        "raw_resolved": len(rows),
        "excluded_count": excluded_count,
        "unvalidatable_count": unvalidatable_count,
        "total_validated": total,
        "correct": correct,
        "incorrect": total - correct,
        "hit_rate": round(correct / total, 3) if total else 0.0,
        "by_direction": by_direction,
        "by_confidence_band": by_band,
    }


def main() -> None:
    parser = make_parser(__file__, "reconstruct the published validation summary")
    parser.add_argument("--days", type=int, default=30, help="lookback window (endpoint default 30)")
    args = parser.parse_args()
    finish(build(args.db, args.days), args)


if __name__ == "__main__":
    main()
