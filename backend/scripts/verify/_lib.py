"""shared plumbing for the verify scripts — stdlib only.

authority direction: these scripts are the spec; endpoints are validated
against them, never vice versa. every formula, token set and threshold
here is a DELIBERATE copy of what the backend is supposed to compute —
nothing imports backend modules. if the backend drifts, the comparison
diverges, and that divergence is the alarm (rfc-worldclass §5.1).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from math import log, sqrt
from pathlib import Path

# duplicated spec constants
MIN_MOVE_PCT = 0.5           # deadband, percent — strict inequality clears it
WILSON_Z = 1.96              # 95% interval
LOG_LOSS_CLIP = 1e-6
UNIFORM_BRIER = 2.0 / 3.0    # uniform 3-class forecast vs any outcome
N_BINS = 5
REL_TOL = 1e-6

CLASSES = ("up", "down", "neutral")
# duplicated from validation/direction_normalizer.py
BULLISH_TOKENS = frozenset({"bullish", "up", "buy", "long", "positive"})
BEARISH_TOKENS = frozenset({"bearish", "down", "sell", "short", "negative"})
NEUTRAL_TOKENS = frozenset({"neutral", "hold", "sideways", "flat", "unclear"})
# duplicated from validation/exclusions.py — enumerated exclusion reason codes
EXCLUSION_CODES = ("GARBAGE_CONFIDENCE_ZERO", "GARBAGE_CONFIDENCE_SUBFLOOR")


# ── direction / outcome semantics ────────────────────────────────────────────

def normalize_direction(raw) -> str:
    if not raw:
        return "unvalidatable"
    token = str(raw).strip().lower()
    if token in BULLISH_TOKENS:
        return "bullish"
    if token in BEARISH_TOKENS:
        return "bearish"
    if token in NEUTRAL_TOKENS:
        return "neutral"
    return "unvalidatable"


def predicted_class(direction) -> str | None:
    return {"bullish": "up", "bearish": "down", "neutral": "neutral"}.get(
        normalize_direction(direction))


def actual_class(change_pct: float) -> str:
    # exactly +/-0.5 stays neutral
    if change_pct > MIN_MOVE_PCT:
        return "up"
    if change_pct < -MIN_MOVE_PCT:
        return "down"
    return "neutral"


def classify_outcome(direction, change_pct: float) -> str:
    """re-derive the label from the persisted move — never prediction_correct."""
    norm = normalize_direction(direction)
    if norm == "unvalidatable":
        return "UNVALIDATABLE"
    if norm == "neutral":
        return "NEUTRAL"
    actual = actual_class(change_pct)
    if actual == "neutral":
        return "NEUTRAL"
    return "CORRECT" if (norm == "bullish") == (actual == "up") else "INCORRECT"


def wilson_95(correct: int, n: int) -> list[float] | None:
    if n == 0:
        return None
    z = WILSON_Z
    p = correct / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


# ── probabilistic scoring suite (calibration family) ─────────────────────────

def forecast_vector(direction, confidence: float) -> dict[str, float] | None:
    # predicted class gets p=confidence; other two split the remainder
    cls = predicted_class(direction)
    if cls is None:
        return None
    conf = min(1.0, max(0.0, float(confidence)))
    residual = (1.0 - conf) / 2.0
    return {k: (conf if k == cls else residual) for k in CLASSES}


def climatology(actuals: list[str]) -> dict[str, float]:
    n = len(actuals)
    if n == 0:
        return {k: 1.0 / 3.0 for k in CLASSES}
    return {k: actuals.count(k) / n for k in CLASSES}


def brier(probs: dict[str, float], actual: str) -> float:
    return sum((probs.get(k, 0.0) - (1.0 if k == actual else 0.0)) ** 2 for k in CLASSES)


def bin_slices(n: int, n_bins: int = N_BINS) -> list[tuple[int, int]]:
    # equal-count edges i*n//k — never an empty bin
    k = min(n_bins, n)
    if k <= 0:
        return []
    edges = [(i * n) // k for i in range(k + 1)]
    return [(edges[i], edges[i + 1]) for i in range(k) if edges[i + 1] > edges[i]]


def reliability_bins(records: list[tuple[float, bool]]) -> list[dict]:
    ordered = sorted(records, key=lambda rec: rec[0])
    bins: list[dict] = []
    for start, end in bin_slices(len(ordered)):
        chunk = ordered[start:end]
        n_b = len(chunk)
        mean_conf = sum(c for c, _ in chunk) / n_b
        hit_rate = sum(1 for _, h in chunk if h) / n_b
        bins.append({"n": n_b, "mean_confidence": round(mean_conf, 4),
                     "hit_rate": round(hit_rate, 4), "gap": round(hit_rate - mean_conf, 4)})
    return bins


def ece(bins: list[dict]) -> float | None:
    total = sum(b["n"] for b in bins)
    if total == 0:
        return None
    # rounded per-bin gap on purpose — matches published value
    return round(sum(b["n"] * abs(b["gap"]) for b in bins) / total, 4)


def murphy(entries: list[tuple[float, dict, str]]) -> dict | None:
    # BS = REL - RES + UNC over the same equal-count confidence bins
    n = len(entries)
    if n == 0:
        return None
    ordered = sorted(entries, key=lambda e: e[0])
    o_bar = climatology([a for _, _, a in ordered])
    rel = res = 0.0
    for start, end in bin_slices(n):
        chunk = ordered[start:end]
        n_b = len(chunk)
        p_bar = {k: sum(p[k] for _, p, _ in chunk) / n_b for k in CLASSES}
        o_bar_b = climatology([a for _, _, a in chunk])
        rel += n_b * sum((p_bar[k] - o_bar_b[k]) ** 2 for k in CLASSES)
        res += n_b * sum((o_bar_b[k] - o_bar[k]) ** 2 for k in CLASSES)
    unc = sum(o_bar[k] * (1.0 - o_bar[k]) for k in CLASSES)
    return {"rel": round(rel / n, 4), "res": round(res / n, 4), "unc": round(unc, 4)}


def score_rows(rows: list[dict]) -> dict:
    """full scoring suite over resolved rows — neutrals scored, no abstention."""
    scored: list[tuple[float, dict, str, bool]] = []
    for row in rows:
        change, conf = row.get("actual_price_change_pct"), row.get("confidence")
        if change is None or conf is None:
            continue
        try:
            conf_f, change_f = float(conf), float(change)
        except (TypeError, ValueError):
            continue
        probs = forecast_vector(row.get("predicted_direction"), conf_f)
        if probs is None:
            continue
        actual = actual_class(change_f)
        scored.append((conf_f, probs, actual,
                       predicted_class(row.get("predicted_direction")) == actual))
    n = len(scored)
    if n == 0:
        return {"n_scored": 0, "brier": None, "log_loss": None,
                "brier_uniform": None, "brier_climatology": None,
                "bss_vs_climatology": None, "bss_vs_uniform": None,
                "reliability": [], "ece": None, "murphy": None}
    actuals = [a for _, _, a, _ in scored]
    clim = climatology(actuals)
    bs = sum(brier(p, a) for _, p, a, _ in scored) / n
    mean_ll = sum(-log(max(p.get(a, 0.0), LOG_LOSS_CLIP)) for _, p, a, _ in scored) / n
    bs_clim = sum(brier(clim, a) for a in actuals) / n
    bins = reliability_bins([(c, h) for c, _, _, h in scored])
    return {
        "n_scored": n,
        "brier": round(bs, 4),
        "log_loss": round(mean_ll, 4),
        "brier_uniform": round(UNIFORM_BRIER, 4),
        "brier_climatology": round(bs_clim, 4),
        # BSS undefined against a perfect (zero) reference
        "bss_vs_climatology": round(1.0 - bs / bs_clim, 4) if bs_clim else None,
        "bss_vs_uniform": round(1.0 - bs / UNIFORM_BRIER, 4),
        "reliability": bins,
        "ece": ece(bins),
        "murphy": murphy([(c, p, a) for c, p, a, _ in scored]),
    }


# ── db access ────────────────────────────────────────────────────────────────

def default_db(script_file: str) -> str:
    # backend/aussieintel.db, two levels above scripts/verify/
    return str(Path(script_file).resolve().parents[2] / "aussieintel.db")


def query(db_path: str, sql: str, params=()) -> list[dict]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # never writes
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


_RESOLVED_SQL = (
    "SELECT predicted_direction, confidence, actual_price_change_pct, actual_driver "
    "FROM prediction_log WHERE resolved_at IS NOT NULL "
    "AND actual_price_change_pct IS NOT NULL{extra} ORDER BY rowid"
)


def resolved_prediction_rows(db_path: str, include_excluded: bool = False) -> list[dict]:
    """resolved prediction_log rows. excluded_from_stats rows never count —
    the spec. include_excluded=True is the contaminated (pre-A1) variant,
    kept computable so before/after pairs stay visible on any db."""
    if include_excluded:
        return query(db_path, _RESOLVED_SQL.format(extra=""))
    try:
        return query(db_path, _RESOLVED_SQL.format(
            extra=" AND (excluded_from_stats IS NULL OR excluded_from_stats = 0)"))
    except sqlite3.OperationalError:
        # pre-migration db without the column
        return query(db_path, _RESOLVED_SQL.format(extra=""))


def exclusion_stats(db_path: str) -> dict:
    """resolved rows dropped by the exclusion filter: {count, by_reason}."""
    try:
        rows = query(db_path, (
            "SELECT exclusion_reason, COUNT(*) AS n FROM prediction_log "
            "WHERE resolved_at IS NOT NULL AND actual_price_change_pct IS NOT NULL "
            "AND excluded_from_stats = 1 GROUP BY exclusion_reason"))
    except sqlite3.OperationalError:
        # pre-migration db without the column
        rows = []
    by_reason = {(r["exclusion_reason"] or "UNSPECIFIED"): r["n"] for r in rows}
    return {"count": sum(by_reason.values()), "by_reason": by_reason}


def split_horizons(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    # '24h' in actual_driver marks the provisional resolver; everything else 7d
    rows_24h: list[dict] = []
    rows_7d: list[dict] = []
    for r in rows:
        target = rows_24h if "24h" in (r.get("actual_driver") or "").lower() else rows_7d
        target.append(r)
    return rows_24h, rows_7d


# ── comparison / cli contract ────────────────────────────────────────────────

def _fmt(v) -> str:
    return json.dumps(v, ensure_ascii=True, default=str)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def diff_fields(recon, actual, skip=frozenset(), path="") -> list[str]:
    """line-per-field diff — walks only fields the reconstruction owns."""
    diffs: list[str] = []
    if isinstance(recon, dict):
        if not isinstance(actual, dict):
            diffs.append(f"{path or '.'}: recomputed={_fmt(recon)} endpoint={_fmt(actual)}")
            return diffs
        for key, want in recon.items():
            if key in skip:
                continue
            sub = f"{path}.{key}" if path else key
            if key not in actual:
                diffs.append(f"{sub}: MISSING from endpoint (recomputed={_fmt(want)})")
            else:
                diffs.extend(diff_fields(want, actual[key], skip, sub))
        return diffs
    if isinstance(recon, (list, tuple)):
        if not isinstance(actual, (list, tuple)):
            diffs.append(f"{path}: recomputed={_fmt(list(recon))} endpoint={_fmt(actual)}")
            return diffs
        if len(recon) != len(actual):
            diffs.append(f"{path}: length recomputed={len(recon)} endpoint={len(actual)}")
            return diffs
        for i, (w, a) in enumerate(zip(recon, actual)):
            diffs.extend(diff_fields(w, a, skip, f"{path}[{i}]"))
        return diffs
    if _is_num(recon) and _is_num(actual):
        # relative for floats, absolute floor near zero
        if abs(recon - actual) > REL_TOL * max(1.0, abs(recon), abs(actual)):
            diffs.append(f"{path}: recomputed={_fmt(recon)} endpoint={_fmt(actual)}")
        return diffs
    if recon != actual:
        diffs.append(f"{path}: recomputed={_fmt(recon)} endpoint={_fmt(actual)}")
    return diffs


def make_parser(script_file: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--db", default=default_db(script_file),
                   help="sqlite db path (default: backend/aussieintel.db)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--endpoint", help="live endpoint URL to compare against")
    g.add_argument("--json", dest="json_path",
                   help="endpoint response saved to a json file")
    return p


def load_actual(args):
    if args.endpoint:
        with urllib.request.urlopen(args.endpoint, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    with open(args.json_path, encoding="utf-8") as fh:
        return json.load(fh)


def finish(recon: dict, args, unwrap=(), skip=frozenset()) -> None:
    """shared tail: print reconstruction, or compare and exit 0/1."""
    if not args.endpoint and not args.json_path:
        print(json.dumps(recon, indent=2, ensure_ascii=True))
        sys.exit(0)
    actual = load_actual(args)
    for key in unwrap:
        if not isinstance(actual, dict) or key not in actual:
            print(f"MISMATCH - endpoint response has no '{key}' envelope")
            sys.exit(1)
        actual = actual[key]
    diffs = diff_fields(recon, actual, skip=frozenset(skip))
    if diffs:
        print(f"MISMATCH - {len(diffs)} field(s) diverge:")
        for line in diffs:
            print(f"  {line}")
        sys.exit(1)
    print(f"OK - endpoint matches reconstruction within {REL_TOL} tolerance")
    sys.exit(0)
