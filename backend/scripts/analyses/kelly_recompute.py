"""Retroactive flat-vs-quarter-Kelly paper-P&L recompute.

Analysis lane (Prediction Masters directive, Phase B corrections item 2).
Data: git-tracked production DB snapshot (--db). Read-only, stdlib only,
imports nothing from backend/ — formulas duplicated on purpose from
services/position_sizer.py so drift is detectable:

  kelly_raw   = W - (1 - W) / R          (W = shrunk win rate, R = payoff ratio)
  W_shrunk    = prior + (W - prior) * n / (n + K), K = 20, prior = breakeven
  stake       = max(0, kelly_raw) * 0.25 (quarter-Kelly)  vs  flat 5%

Walk-forward, strictly as-of: each prediction's stake uses only predictions
RESOLVED before its own predicted_at (no look-ahead). Non-neutral rows only
(neutral = no position, both strategies). Bankroll compounds multiplicatively.
"""

import argparse
import json
import sqlite3

K_SHRINK = 20          # position_sizer: "no edge until ~20 resolved"
KELLY_FRACTION = 0.25  # DEFAULT_KELLY_FRACTION
FLAT_STAKE = 0.05
STAKE_CAP = 0.25       # sanity cap so one row cannot bet the book

_BULL = {"bullish", "up"}
_BEAR = {"bearish", "down"}


def _norm_direction(token: str) -> str:
    t = (token or "").strip().lower()
    if t in _BULL:
        return "bullish"
    if t in _BEAR:
        return "bearish"
    return "neutral"


def load_rows(db_path: str) -> list[dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = []
    for r in con.execute(
        """SELECT ticker, predicted_direction, predicted_at, actual_price_change_pct
           FROM prediction_log
           WHERE actual_direction IS NOT NULL AND actual_price_change_pct IS NOT NULL
           ORDER BY predicted_at"""
    ):
        d = _norm_direction(r["predicted_direction"])
        if d == "neutral":
            continue
        signed = r["actual_price_change_pct"] if d == "bullish" else -r["actual_price_change_pct"]
        rows.append({"ticker": r["ticker"], "ret_pct": signed, "at": r["predicted_at"]})
    con.close()
    return rows


def _kelly_stake(prior_rets: list[float]) -> float:
    n = len(prior_rets)
    wins = [x for x in prior_rets if x > 0]
    losses = [-x for x in prior_rets if x < 0]
    payoff = (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if wins and losses else 1.0
    breakeven = 1.0 / (1.0 + payoff)
    win_rate = len(wins) / n if n else breakeven
    w = breakeven + (win_rate - breakeven) * n / (n + K_SHRINK)
    kelly_raw = w - (1.0 - w) / payoff
    return min(max(kelly_raw, 0.0) * KELLY_FRACTION, STAKE_CAP)


def simulate(rows: list[dict], per_ticker: bool) -> dict:
    flat = kelly = 1.0
    flat_peak = kelly_peak = 1.0
    flat_dd = kelly_dd = 0.0
    staked = 0
    history: dict[str, list[float]] = {}
    for row in rows:
        key = row["ticker"] if per_ticker else "_pooled"
        prior = history.setdefault(key, [])
        stake = _kelly_stake(prior)
        r = row["ret_pct"] / 100.0
        flat *= 1.0 + FLAT_STAKE * r
        kelly *= 1.0 + stake * r
        if stake > 0:
            staked += 1
        flat_peak = max(flat_peak, flat)
        kelly_peak = max(kelly_peak, kelly)
        flat_dd = max(flat_dd, 1.0 - flat / flat_peak)
        kelly_dd = max(kelly_dd, 1.0 - kelly / kelly_peak)
        prior.append(row["ret_pct"])
    return {
        "mode": "per_ticker" if per_ticker else "pooled",
        "n_positions": len(rows),
        "n_kelly_nonzero_stakes": staked,
        "flat_final_bankroll": round(flat, 4),
        "kelly_final_bankroll": round(kelly, 4),
        "flat_max_drawdown": round(flat_dd, 4),
        "kelly_max_drawdown": round(kelly_dd, 4),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    rows = load_rows(args.db)
    wins = sum(1 for r in rows if r["ret_pct"] > 0)
    print(
        json.dumps(
            {
                "flat_stake": FLAT_STAKE,
                "kelly_fraction": KELLY_FRACTION,
                "k_shrink": K_SHRINK,
                "directional_rows": len(rows),
                "directional_win_rate": round(wins / len(rows), 4) if rows else None,
                "runs": [simulate(rows, per_ticker=True), simulate(rows, per_ticker=False)],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
