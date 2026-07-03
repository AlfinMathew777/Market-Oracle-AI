#!/usr/bin/env python3
"""recompute GET /api/accuracy/calibration ('data' envelope) from raw rows.

full scoring suite over the same resolved prediction_log rows the track
record uses: 3-class brier (predicted class p=confidence, others split
the remainder), log loss (clip 1e-6), BSS vs uniform (2/3) and vs class
frequencies, equal-count reliability bins (edges i*N//k), ECE, murphy.
neutrals ARE scored — probabilistic scoring never abstains.
generated_at is a server timestamp and is not reconstructable — skipped.
"""

from __future__ import annotations

from _lib import (
    MIN_MOVE_PCT, finish, make_parser, resolved_prediction_rows,
    score_rows, split_horizons,
)


def main() -> None:
    args = make_parser(__file__, "reconstruct the published calibration suite").parse_args()
    rows_24h, rows_7d = split_horizons(resolved_prediction_rows(args.db))
    all_rows = [*rows_24h, *rows_7d]  # endpoint concatenates 24h first — bin order matters
    recon = {
        **score_rows(all_rows),
        "n": len(all_rows),
        "deadband_pct": MIN_MOVE_PCT,
        "horizons": {
            "provisional_24h": score_rows(rows_24h),
            "authoritative_7d": score_rows(rows_7d),
        },
    }
    finish(recon, args, unwrap=("data",))


if __name__ == "__main__":
    main()
