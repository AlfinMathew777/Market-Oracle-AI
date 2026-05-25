"""
One-shot historical revalidation script for prediction_log.

What this fixes
---------------
1. Neutral scoring bug: neutral-direction rows were written with
   prediction_correct=0 (INCORRECT). Neutral predictions make no
   directional claim and must carry prediction_correct=NULL.

2. Unvalidatable tokens: any direction token not recognised by
   direction_normalizer is set to prediction_correct=NULL so it
   is not counted in hit-rate calculations.

Safety
------
- Read-only mode by default (--dry-run). Pass --commit to persist.
- Only touches rows where prediction_correct IS NOT NULL (i.e. already
  "resolved") — never creates new resolutions.
- Prints a full diff before writing anything.

Usage
-----
    cd backend
    python scripts/revalidate_historical.py           # dry-run
    python scripts/revalidate_historical.py --commit  # write
"""

import argparse
import sys
import os

# Allow running from backend/ or backend/scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from validation.direction_normalizer import normalize_direction, is_actionable, NEUTRAL_TOKENS

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aussieintel.db")


def _fetch_resolved(conn: sqlite3.Connection) -> list[dict]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, ticker, predicted_direction, confidence, prediction_correct, excluded_from_stats
        FROM prediction_log
        WHERE prediction_correct IS NOT NULL
        ORDER BY id
    """)
    return [dict(r) for r in cur.fetchall()]


def _classify_fix(row: dict) -> tuple[str, str] | None:
    """
    Return (fix_type, description) if this row needs correcting, else None.

    fix_type:
      "neutral_scored"     — direction is neutral but prediction_correct != NULL
      "unvalidatable"      — direction token unrecognised; should not be scored
    """
    direction = (row["predicted_direction"] or "").strip().lower()
    norm = normalize_direction(direction)
    current_correct = row["prediction_correct"]

    if norm == "neutral" and current_correct is not None:
        return (
            "neutral_scored",
            f"{row['ticker']} direction={direction!r} prediction_correct={current_correct} -> NULL",
        )

    if norm == "unvalidatable" and current_correct is not None:
        return (
            "unvalidatable",
            f"{row['ticker']} direction={direction!r} prediction_correct={current_correct} -> NULL",
        )

    return None


def run(dry_run: bool) -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = _fetch_resolved(conn)
    print(f"Inspecting {len(rows)} resolved rows in prediction_log …\n")

    fixes: list[tuple[str, str, str]] = []  # (id, fix_type, description)
    for row in rows:
        result = _classify_fix(row)
        if result:
            fix_type, desc = result
            fixes.append((row["id"], fix_type, desc))

    if not fixes:
        print("Nothing to fix — all resolved rows have valid direction tokens.")
        conn.close()
        return

    # Group by fix type
    neutral_fixes = [(rid, desc) for rid, ft, desc in fixes if ft == "neutral_scored"]
    unval_fixes   = [(rid, desc) for rid, ft, desc in fixes if ft == "unvalidatable"]

    print(f"Found {len(fixes)} rows needing correction:")
    print(f"  {len(neutral_fixes)} neutral rows incorrectly scored as CORRECT/INCORRECT")
    print(f"  {len(unval_fixes)} rows with unrecognised direction tokens\n")

    for _, ft, desc in fixes:
        label = "[neutral_scored]" if ft == "neutral_scored" else "[unvalidatable] "
        print(f"  {label} {desc}")

    if dry_run:
        print("\nDry run — no changes written. Pass --commit to persist.")
        conn.close()
        return

    print("\nWriting fixes …")
    ids_to_null = [rid for rid, _, _ in fixes]
    cur = conn.cursor()
    cur.executemany(
        "UPDATE prediction_log SET prediction_correct = NULL WHERE id = ?",
        [(rid,) for rid in ids_to_null],
    )
    conn.commit()
    print(f"Updated {cur.rowcount} rows — prediction_correct set to NULL.")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revalidate historical prediction_log entries")
    parser.add_argument("--commit", action="store_true", help="Write changes (default: dry-run)")
    args = parser.parse_args()
    run(dry_run=not args.commit)
