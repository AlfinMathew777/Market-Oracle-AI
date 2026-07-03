#!/usr/bin/env python3
"""Amendment-2 divergence sweep across duplicate endpoint clusters.

During the Stage 2a access-log window, every member of each duplicate
cluster is fetched and semantically-equivalent fields are compared.
ANY divergence is an andon finding: it tells the dedup decision which
duplicate was WRONG, not just which was unused.

Independence rule: imports NOTHING from backend/. stdlib only.

Usage:
    python verify_duplicates.py --base https://staging.up.railway.app \
        [--tag pre-dedup] [--out path.md] [--api-key KEY]

Exit 0 = no divergence, 2 = any DIVERGE (andon), 1 = operational failure.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# counts must match exactly; pct fields tolerate cross-endpoint rounding
# (one side rounds to 1 decimal, another to 2)
COUNT_TOL = 0.0
PCT_TOL = 0.051

# duplicate clusters from rfc §1.2 — paths confirmed against routes/
ACCURACY_EPS = ["/api/predict/accuracy", "/api/predictions/accuracy", "/api/accuracy/summary"]
CALIBRATION_EPS = ["/api/predictions/calibration", "/api/accuracy/calibration"]
# same nominal limit on both sides so counts are comparable
HISTORY_EPS = ["/api/predict/history?limit=100", "/api/predictions/history?limit=100&days=365"]
BACKTEST_EPS = ["/api/predictions/backtest?days=30", "/api/backtest/runs"]


def get_path(obj, *keys):
    # tolerant nested lookup
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def compare_values(values: dict, tol: float = 0.0) -> str:
    """AGREE / DIVERGE / NOT-COMPARABLE across endpoint -> value pairs.

    None values (endpoint unreachable or field absent) drop out of the
    comparison; fewer than two remaining values is NOT-COMPARABLE.
    """
    present = [v for v in values.values() if v is not None]
    if len(present) < 2:
        return "NOT-COMPARABLE"
    first = present[0]
    for v in present[1:]:
        if isinstance(first, (int, float)) and isinstance(v, (int, float)):
            if abs(v - first) > tol:
                return "DIVERGE"
        elif v != first:
            return "DIVERGE"
    return "AGREE"


def _field(name: str, values: dict, tol: float = 0.0, note: str = "",
           verdict: str | None = None) -> dict:
    return {"field": name, "values": values,
            "verdict": verdict or compare_values(values, tol), "note": note}


def accuracy_fields(payloads: dict) -> list[dict]:
    """Cluster a — three accuracy endpoints, three different tables.

    mapping (resolved directional predictions):
      /api/predict/accuracy      data.total / data.correct / data.accuracy_pct   (simulations)
      /api/predictions/accuracy  data.resolved_predictions / data.correct_predictions
                                 / data.direction_accuracy_pct                   (prediction_log)
      /api/accuracy/summary      resolved_predictions / correct / accuracy_pct   (reasoning_predictions, no envelope)
    """
    a, b, c = (payloads.get(e) for e in ACCURACY_EPS)
    return [
        _field("resolved_count", {
            ACCURACY_EPS[0]: get_path(a, "data", "total"),
            ACCURACY_EPS[1]: get_path(b, "data", "resolved_predictions"),
            ACCURACY_EPS[2]: get_path(c, "resolved_predictions"),
        }, COUNT_TOL, note="three different source tables — divergence expected to inform dedup"),
        _field("correct_count", {
            ACCURACY_EPS[0]: get_path(a, "data", "correct"),
            ACCURACY_EPS[1]: get_path(b, "data", "correct_predictions"),
            ACCURACY_EPS[2]: get_path(c, "correct"),
        }, COUNT_TOL),
        _field("accuracy_pct", {
            ACCURACY_EPS[0]: get_path(a, "data", "accuracy_pct"),
            ACCURACY_EPS[1]: get_path(b, "data", "direction_accuracy_pct"),
            ACCURACY_EPS[2]: get_path(c, "accuracy_pct"),
        }, PCT_TOL),
    ]


def calibration_fields(payloads: dict) -> list[dict]:
    """Cluster b — two calibration endpoints.

    mapping (resolved rows scored):
      /api/predictions/calibration  data.sample_size  (prediction_log, fixed-width buckets)
      /api/accuracy/calibration     data.n            (prediction_log, brier suite, equal-count bins)
    bin structures differ by construction — recorded NOT-COMPARABLE, not diverged.
    """
    a, b = (payloads.get(e) for e in CALIBRATION_EPS)
    return [
        _field("resolved_sample_size", {
            CALIBRATION_EPS[0]: get_path(a, "data", "sample_size"),
            CALIBRATION_EPS[1]: get_path(b, "data", "n"),
        }, COUNT_TOL),
        _field("reliability_bins", {e: None for e in CALIBRATION_EPS},
               verdict="NOT-COMPARABLE",
               note="fixed-width confidence buckets vs equal-count reliability bins — different constructions"),
    ]


def history_fields(payloads: dict) -> list[dict]:
    """Cluster c — two history endpoints, two different tables.

    mapping (both fetched with limit=100):
      /api/predict/history       count + data[].ticker  (simulations, no day window)
      /api/predictions/history   count + data[].ticker  (prediction_log, 365-day window)
    """
    a, b = (payloads.get(e) for e in HISTORY_EPS)

    def tickers(payload):
        rows = get_path(payload, "data")
        if not isinstance(rows, list):
            return None
        return sorted({r.get("ticker") for r in rows if isinstance(r, dict)})

    return [
        _field("row_count", {
            HISTORY_EPS[0]: get_path(a, "count"),
            HISTORY_EPS[1]: get_path(b, "count"),
        }, COUNT_TOL, note="different source tables (simulations vs prediction_log)"),
        _field("distinct_tickers", {
            HISTORY_EPS[0]: tickers(a),
            HISTORY_EPS[1]: tickers(b),
        }),
    ]


def backtest_fields(payloads: dict) -> list[dict]:
    """Cluster d — shape differs; overlapping semantics only.

    /api/predictions/backtest  scores swarm prediction_log rows against yfinance
    /api/backtest/runs         lists TA-rule engine runs; the list response
                               carries NO metrics column
    no shared population, no shared metric — recorded NOT-COMPARABLE explicitly.
    reachability and counts are still captured as sweep evidence.
    """
    a, b = (payloads.get(e) for e in BACKTEST_EPS)
    runs = get_path(b, "data")
    completed = (sum(1 for r in runs if isinstance(r, dict) and r.get("status") == "completed")
                 if isinstance(runs, list) else None)
    return [
        _field("hit_rate", {e: None for e in BACKTEST_EPS}, verdict="NOT-COMPARABLE",
               note="swarm-prediction scoring vs TA-engine run registry — different populations; "
                    "/api/backtest/runs response carries no metrics"),
        _field("swarm_sample_size (info only)", {
            BACKTEST_EPS[0]: get_path(a, "data", "sample_size"),
            BACKTEST_EPS[1]: None,
        }, verdict="NOT-COMPARABLE", note="no counterpart field in /api/backtest/runs"),
        _field("completed_run_count (info only)", {
            BACKTEST_EPS[0]: None,
            BACKTEST_EPS[1]: completed,
        }, verdict="NOT-COMPARABLE", note="no counterpart field in /api/predictions/backtest"),
    ]


CLUSTERS = [
    ("accuracy", ACCURACY_EPS, accuracy_fields),
    ("calibration", CALIBRATION_EPS, calibration_fields),
    ("history", HISTORY_EPS, history_fields),
    ("backtest", BACKTEST_EPS, backtest_fields),
]


def fetch_json(base: str, path: str, api_key: str | None = None,
               timeout: float = 20.0) -> tuple[dict | None, str | None]:
    # graceful failure — record, never raise
    url = base.rstrip("/") + path
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp), None
    except Exception as exc:  # noqa: BLE001 — sweep must survive any endpoint failure
        return None, f"{type(exc).__name__}: {exc}"


def cluster_verdict(fields: list[dict], errors: dict) -> str:
    verdicts = [f["verdict"] for f in fields]
    if any(v == "DIVERGE" for v in verdicts):
        return "DIVERGE"
    if errors and not any(v == "AGREE" for v in verdicts):
        return "UNREACHABLE"
    if any(v == "AGREE" for v in verdicts):
        return "AGREE"
    return "NOT-COMPARABLE"


def sweep(base: str, api_key: str | None = None) -> list[dict]:
    results = []
    for name, endpoints, extractor in CLUSTERS:
        payloads: dict = {}
        errors: dict = {}
        for ep in endpoints:
            payload, err = fetch_json(base, ep, api_key)
            payloads[ep] = payload
            if err:
                errors[ep] = err
        fields = extractor(payloads)
        results.append({"cluster": name, "endpoints": endpoints,
                        "errors": errors, "fields": fields,
                        "verdict": cluster_verdict(fields, errors)})
    return results


def exit_code(clusters: list[dict]) -> int:
    # andon: any diverge trips exit 2
    if any(c["verdict"] == "DIVERGE" for c in clusters):
        return 2
    # every endpoint down = operational failure
    total_eps = sum(len(c["endpoints"]) for c in clusters)
    total_errs = sum(len(c["errors"]) for c in clusters)
    if total_eps and total_errs == total_eps:
        return 1
    return 0


def render_report(clusters: list[dict], base: str, tag: str) -> str:
    lines = [
        f"# Duplicate-endpoint divergence sweep — {tag}",
        "",
        f"Base: `{base}`  |  RFC amendment 2 — any DIVERGE is an andon finding",
        "",
    ]
    for c in clusters:
        lines += [f"## Cluster: {c['cluster']} — **{c['verdict']}**", ""]
        for ep in c["endpoints"]:
            status = c["errors"].get(ep, "ok")
            lines.append(f"- `{ep}` — {status}")
        lines += ["", "| field | values | verdict | note |", "|---|---|---|---|"]
        for f in c["fields"]:
            vals = "; ".join(f"`{ep}` = {v}" for ep, v in f["values"].items())
            lines.append(f"| {f['field']} | {vals} | {f['verdict']} | {f['note']} |")
        lines.append("")
    diverged = [c["cluster"] for c in clusters if c["verdict"] == "DIVERGE"]
    lines.append(f"**Result:** {'DIVERGE in ' + ', '.join(diverged) + ' — ANDON' if diverged else 'no divergence detected'}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="backend base url, e.g. https://staging.up.railway.app")
    ap.add_argument("--tag", default="untagged", help="filename suffix for the default report path")
    ap.add_argument("--out", default=None, help="report path (default docs/postmortems/duplicates-sweep-<tag>.md)")
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()

    try:
        clusters = sweep(args.base, args.api_key)
        repo_root = Path(__file__).resolve().parents[3]
        out = Path(args.out) if args.out else repo_root / "docs" / "postmortems" / f"duplicates-sweep-{args.tag}.md"
        report = render_report(clusters, args.base, args.tag)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(report)
        print(f"report written to {out}")
        return exit_code(clusters)
    except Exception as exc:  # noqa: BLE001 — operational failure path
        print(f"OPERATIONAL FAILURE: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
