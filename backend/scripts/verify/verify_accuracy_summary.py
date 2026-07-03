#!/usr/bin/env python3
"""recompute GET /api/accuracy/summary from raw reasoning_predictions rows.

published semantics duplicated exactly: window compares prediction_timestamp
strings against NAIVE LOCAL now (not utc — endpoint behaviour), confidence_score
is a 0-100 integer, resolved = outcome_status != 'PENDING' (EXPIRED counts as
resolved but never as correct), accuracy_pct = correct/resolved*100,
avg_return over non-null returns of resolved rows only.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from _lib import finish, make_parser, query


def build(db_path: str, days: int, ticker: str | None, direction: str | None) -> dict:
    # naive local now — deliberate copy of the endpoint's window
    since = (datetime.now() - timedelta(days=days)).isoformat()
    sql = ("SELECT outcome_status, actual_return_pct, confidence_score "
           "FROM reasoning_predictions WHERE prediction_timestamp >= ?")
    params: list = [since]
    if ticker:
        sql += " AND stock_ticker = ?"
        params.append(ticker)
    if direction:
        sql += " AND direction = ?"
        params.append(direction)
    rows = query(db_path, sql, params)

    resolved = [r for r in rows if r["outcome_status"] != "PENDING"]

    def count(status: str) -> int:
        return sum(1 for r in rows if r["outcome_status"] == status)

    correct = count("CORRECT")
    returns = [r["actual_return_pct"] for r in resolved if r["actual_return_pct"] is not None]
    confs = [r["confidence_score"] for r in rows if r["confidence_score"] is not None]
    return {
        "scope": ticker or direction or "overall",
        "total_predictions": len(rows),
        "resolved_predictions": len(resolved),
        "correct": correct,
        "incorrect": count("INCORRECT"),
        "partial": count("PARTIAL"),
        "stopped_out": count("STOPPED_OUT"),
        "accuracy_pct": round(correct / len(resolved) * 100, 2) if resolved else 0.0,
        "avg_return_pct": round(sum(returns) / len(returns), 4) if returns else 0,
        "avg_confidence": round(sum(confs) / len(confs), 2) if confs else 0,
    }


def main() -> None:
    parser = make_parser(__file__, "reconstruct the published accuracy summary")
    parser.add_argument("--days", type=int, default=90, help="lookback window (endpoint default 90)")
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--direction", default=None)
    args = parser.parse_args()
    finish(build(args.db, args.days, args.ticker, args.direction), args)


if __name__ == "__main__":
    main()
