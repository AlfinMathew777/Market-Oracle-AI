"""Spread-error calibration: does agent-vote disagreement predict miss size?

Analysis lane (Prediction Masters directive, Phase B corrections item 2).
Data: a git-tracked production DB snapshot (pass --db). Read-only, stdlib only,
imports nothing from backend/ — same independence rule as scripts/verify.

Protocol (pre-registered in docs/extraction-table.md row 2, adapted to N<150):
  - rows: prediction_log, resolved, with agent vote counts
  - dispersion = normalized entropy of (bullish, bearish, neutral) vote shares
  - forecast vector: p(predicted class) = confidence, others split evenly
    (duplicated from trust/scoring.py spec on purpose)
  - actual class: +-0.5% deadband, strict inequality (verify-script spec)
  - Brier per dispersion tercile; CLUSTER bootstrap 95% CI (clusters = shared
    resolution window, i.e. identical ticker+entry+exit), seed 42, 10k draws
  - segmented: all protocols vs v2-only (7-trading-day resolution notes)
"""

import argparse
import json
import math
import random
import sqlite3

DEADBAND_PCT = 0.5
SEED = 42
N_BOOT = 10_000

_BULL = {"bullish", "up"}
_BEAR = {"bearish", "down"}


def _norm_direction(token: str) -> str:
    t = (token or "").strip().lower()
    if t in _BULL:
        return "bullish"
    if t in _BEAR:
        return "bearish"
    return "neutral"


def _actual_class(change_pct: float) -> str:
    if change_pct > DEADBAND_PCT:
        return "bullish"
    if change_pct < -DEADBAND_PCT:
        return "bearish"
    return "neutral"


def _forecast_vector(direction: str, confidence: float) -> dict:
    conf = min(max(confidence, 0.0), 1.0)
    rest = (1.0 - conf) / 2.0
    return {c: (conf if c == direction else rest) for c in ("bullish", "bearish", "neutral")}


def _brier(probs: dict, actual: str) -> float:
    return sum((probs[c] - (1.0 if c == actual else 0.0)) ** 2 for c in probs)


def _entropy_norm(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return h / math.log(3)


def load_rows(db_path: str) -> list[dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = []
    for r in con.execute(
        """SELECT ticker, predicted_direction, confidence, agent_bullish,
                  agent_bearish, agent_neutral, actual_price_change_pct,
                  resolution_notes, predicted_at
           FROM prediction_log
           WHERE actual_direction IS NOT NULL AND agent_bullish IS NOT NULL
                 AND confidence IS NOT NULL AND actual_price_change_pct IS NOT NULL"""
    ):
        votes = [r["agent_bullish"], r["agent_bearish"], r["agent_neutral"]]
        direction = _norm_direction(r["predicted_direction"])
        rows.append(
            {
                "dispersion": _entropy_norm(votes),
                "brier": _brier(
                    _forecast_vector(direction, r["confidence"]),
                    _actual_class(r["actual_price_change_pct"]),
                ),
                # identical resolution window => not an independent observation
                "cluster": f"{r['ticker']}|{r['resolution_notes']}",
                "protocol": "v2" if r["resolution_notes"] else "v1",
            }
        )
    con.close()
    return rows


def _cluster_bootstrap_mean_ci(rows: list[dict], rng: random.Random) -> tuple[float, float, float]:
    clusters: dict[str, list[float]] = {}
    for row in rows:
        clusters.setdefault(row["cluster"], []).append(row["brier"])
    keys = sorted(clusters)
    point = sum(r["brier"] for r in rows) / len(rows)
    means = []
    for _ in range(N_BOOT):
        sample = [b for k in (rng.choice(keys) for _ in keys) for b in clusters[k]]
        means.append(sum(sample) / len(sample))
    means.sort()
    return point, means[int(0.025 * N_BOOT)], means[int(0.975 * N_BOOT)]


def analyse(rows: list[dict], label: str) -> dict:
    rng = random.Random(SEED)
    ordered = sorted(rows, key=lambda r: r["dispersion"])
    n = len(ordered)
    terciles = [ordered[: n // 3], ordered[n // 3 : 2 * n // 3], ordered[2 * n // 3 :]]
    out = {"segment": label, "n": n, "n_clusters": len({r["cluster"] for r in rows}), "terciles": []}
    for name, part in zip(("low", "mid", "high"), terciles):
        point, lo, hi = _cluster_bootstrap_mean_ci(part, rng)
        out["terciles"].append(
            {
                "bin": name,
                "n": len(part),
                "dispersion_range": [round(part[0]["dispersion"], 3), round(part[-1]["dispersion"], 3)],
                "brier": round(point, 4),
                "ci95": [round(lo, 4), round(hi, 4)],
            }
        )
    # Spearman rank correlation dispersion vs brier (no scipy: manual ranks)
    def ranks(vals):
        order = sorted(range(len(vals)), key=vals.__getitem__)
        rk = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                rk[order[k]] = avg
            i = j + 1
        return rk

    xs = ranks([r["dispersion"] for r in rows])
    ys = ranks([r["brier"] for r in rows])
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    vx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    vy = math.sqrt(sum((b - my) ** 2 for b in ys))
    out["spearman_dispersion_vs_brier"] = round(cov / (vx * vy), 4) if vx and vy else None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    rows = load_rows(args.db)
    result = {
        "seed": SEED,
        "n_boot": N_BOOT,
        "deadband_pct": DEADBAND_PCT,
        "segments": [
            analyse(rows, "all"),
            analyse([r for r in rows if r["protocol"] == "v2"], "v2_only"),
        ],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
