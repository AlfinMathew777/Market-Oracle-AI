"""Probabilistic forecast scoring — pure functions, no I/O.

World-standard verification of the swarm's directional forecasts:
  - 3-class Brier score (up/down/neutral, one-hot outcomes, range [0, 2])
  - log loss (negative log-likelihood of the realised class)
  - Brier Skill Score vs uniform and climatology baselines
  - equal-count reliability bins + expected calibration error (ECE)
  - Murphy decomposition (reliability, resolution, uncertainty)

Design notes:
  - Direction tokens are normalised through validation.direction_normalizer —
    never hard-coded token comparisons. Unvalidatable tokens return None.
  - The deadband is validation.constants.MIN_MOVE_PCT with the exact boundary
    semantics of validation.outcome_checker.classify_outcome: a move of
    exactly +/-MIN_MOVE_PCT is "neutral" (strict inequality clears the band).
  - NEUTRAL predictions ARE scored. Probabilistic scoring does not abstain:
    "neutral" is a real claim ("the move stays inside the deadband") and is
    rewarded or penalised like any other forecast. This is a feature — it
    removes the survivorship blind spot of hit-rate accounting.
  - Binning is equal-count (quantile), not fixed-width — the honest choice at
    small N (Brocker & Smith 2007).
"""

from __future__ import annotations

import math
from typing import Optional

from validation.constants import MIN_MOVE_PCT
from validation.direction_normalizer import normalize_direction

# canonical outcome classes for the 3-class score.
CLASSES: tuple[str, str, str] = ("up", "down", "neutral")
_DIRECTION_TO_CLASS: dict[str, str] = {"bullish": "up", "bearish": "down", "neutral": "neutral"}
_LOG_LOSS_CLIP: float = 1e-6
# uniform (1/3, 1/3, 1/3) forecast scores 2/3 against ANY outcome — fixed anchor.
_UNIFORM_BRIER: float = 2.0 / 3.0
DEFAULT_N_BINS: int = 5


def predicted_class(direction: Optional[str]) -> Optional[str]:
    """Canonical outcome class for a free-form direction token, or None if unvalidatable."""
    return _DIRECTION_TO_CLASS.get(normalize_direction(direction))


def forecast_vector(direction: Optional[str], confidence: float) -> Optional[dict[str, float]]:
    """Probability vector implied by a direction token and stated confidence.

    The predicted class gets p=confidence; the other two classes split the
    remainder equally. Returns None when the token cannot be normalised
    (unvalidatable). Confidence is clamped into [0, 1].
    """
    cls = predicted_class(direction)
    if cls is None:
        return None
    conf = min(1.0, max(0.0, float(confidence)))
    residual = (1.0 - conf) / 2.0
    return {k: (conf if k == cls else residual) for k in CLASSES}


def actual_class(actual_price_change_pct: float) -> str:
    """Realised outcome class — same strict-inequality deadband as classify_outcome."""
    if actual_price_change_pct > MIN_MOVE_PCT:
        return "up"
    if actual_price_change_pct < -MIN_MOVE_PCT:
        return "down"
    return "neutral"


def brier_score_3class(probs: dict[str, float], actual: str) -> float:
    """Multiclass Brier score: sum over classes of (p_k - o_k)^2, range [0, 2]."""
    return sum((probs.get(k, 0.0) - (1.0 if k == actual else 0.0)) ** 2 for k in CLASSES)


def log_loss(probs: dict[str, float], actual: str) -> float:
    """-ln(p_actual), with p clipped at 1e-6 so a zero never blows up the mean."""
    return -math.log(max(probs.get(actual, 0.0), _LOG_LOSS_CLIP))


def climatology_probs(actual_classes: list[str]) -> dict[str, float]:
    """Class frequencies over the resolved set; uniform (max-entropy) if empty."""
    n = len(actual_classes)
    if n == 0:
        return {k: 1.0 / 3.0 for k in CLASSES}
    return {k: actual_classes.count(k) / n for k in CLASSES}


def brier_skill_score(bs: float, bs_ref: float) -> Optional[float]:
    """BSS = 1 - bs/bs_ref. Positive beats the reference. None if bs_ref is 0."""
    if bs_ref == 0:
        return None
    return 1.0 - bs / bs_ref


def _bin_slices(n: int, n_bins: int) -> list[tuple[int, int]]:
    """Equal-count slice boundaries over n sorted records — never an empty bin."""
    k = min(n_bins, n)
    if k <= 0:
        return []
    edges = [(i * n) // k for i in range(k + 1)]
    return [(edges[i], edges[i + 1]) for i in range(k) if edges[i + 1] > edges[i]]


def reliability_bins(
    records: list[tuple[float, bool]], n_bins: int = DEFAULT_N_BINS
) -> list[dict]:
    """Equal-count (quantile) calibration bins over stated confidence.

    Quantile bins, NOT fixed-width: at small N fixed-width bins leave most
    buckets empty and the occupied ones noise-dominated (Brocker & Smith 2007).
    records: (stated_confidence, prediction_hit). gap = hit_rate - mean_confidence
    (positive → underconfident, negative → overconfident).
    """
    ordered = sorted(records, key=lambda rec: rec[0])
    bins: list[dict] = []
    for start, end in _bin_slices(len(ordered), n_bins):
        chunk = ordered[start:end]
        n_b = len(chunk)
        mean_conf = sum(conf for conf, _ in chunk) / n_b
        hit_rate = sum(1 for _, hit in chunk if hit) / n_b
        bins.append(
            {
                "n": n_b,
                "mean_confidence": round(mean_conf, 4),
                "hit_rate": round(hit_rate, 4),
                "gap": round(hit_rate - mean_conf, 4),
            }
        )
    return bins


def expected_calibration_error(bins: list[dict]) -> Optional[float]:
    """ECE = sum over bins of (n_b / N) * |gap_b|. None when there are no bins."""
    total = sum(b["n"] for b in bins)
    if total == 0:
        return None
    return round(sum(b["n"] * abs(b["gap"]) for b in bins) / total, 4)


def murphy_decomposition(
    entries: list[tuple[float, dict[str, float], str]],
    n_bins: int = DEFAULT_N_BINS,
) -> Optional[dict[str, float]]:
    """Murphy (1973) decomposition of the 3-class Brier score: BS = REL - RES + UNC.

    entries: (stated_confidence, forecast probs, actual class). Bins are the
    same equal-count confidence bins reliability_bins uses, so the identity is
    exact for per-bin-constant forecasts and holds within binning tolerance
    otherwise. REL = (1/N) sum n_b*||p_bar_b - o_bar_b||^2;
    RES = (1/N) sum n_b*||o_bar_b - o_bar||^2; UNC = sum_k o_bar_k(1 - o_bar_k).
    """
    n = len(entries)
    if n == 0:
        return None
    ordered = sorted(entries, key=lambda e: e[0])
    o_bar = climatology_probs([a for _, _, a in ordered])
    rel = res = 0.0
    for start, end in _bin_slices(n, n_bins):
        chunk = ordered[start:end]
        n_b = len(chunk)
        p_bar = {k: sum(p[k] for _, p, _ in chunk) / n_b for k in CLASSES}
        o_bar_b = climatology_probs([a for _, _, a in chunk])
        rel += n_b * sum((p_bar[k] - o_bar_b[k]) ** 2 for k in CLASSES)
        res += n_b * sum((o_bar_b[k] - o_bar[k]) ** 2 for k in CLASSES)
    unc = sum(o_bar[k] * (1.0 - o_bar[k]) for k in CLASSES)
    return {"rel": rel / n, "res": res / n, "unc": unc}


def _extract_scored(rows: list[dict]) -> list[tuple[float, dict[str, float], str, bool]]:
    """(confidence, probs, actual_class, hit) per scoreable row — skips bad rows."""
    scored: list[tuple[float, dict[str, float], str, bool]] = []
    for row in rows:
        change = row.get("actual_price_change_pct")
        conf = row.get("confidence")
        if change is None or conf is None:
            continue
        try:
            conf_f = float(conf)
            change_f = float(change)
        except (TypeError, ValueError):
            continue
        probs = forecast_vector(row.get("predicted_direction"), conf_f)
        if probs is None:
            continue
        actual = actual_class(change_f)
        hit = predicted_class(row.get("predicted_direction")) == actual
        scored.append((conf_f, probs, actual, hit))
    return scored


def score_predictions(rows: list[dict], n_bins: int = DEFAULT_N_BINS) -> dict:
    """Score resolved prediction rows with proper probabilistic metrics.

    Each row needs predicted_direction (free token), confidence (0.0-1.0) and
    actual_price_change_pct. Rows with an unvalidatable direction or a missing
    confidence/actual_price_change_pct are skipped. NEUTRAL predictions ARE
    scored — probabilistic scoring does not abstain: "neutral" is a genuine
    claim that the move stays inside the deadband, and it is rewarded or
    penalised accordingly (unlike hit-rate accounting, which excludes them).

    Pure and side-effect free; input rows are never mutated.
    """
    scored = _extract_scored(rows)
    n = len(scored)
    if n == 0:
        return {
            "n_scored": 0, "brier": None, "log_loss": None,
            "brier_uniform": None, "brier_climatology": None,
            "bss_vs_climatology": None, "bss_vs_uniform": None,
            "reliability": [], "ece": None, "murphy": None,
        }

    actuals = [a for _, _, a, _ in scored]
    clim = climatology_probs(actuals)
    brier = sum(brier_score_3class(p, a) for _, p, a, _ in scored) / n
    mean_ll = sum(log_loss(p, a) for _, p, a, _ in scored) / n
    brier_clim = sum(brier_score_3class(clim, a) for a in actuals) / n
    bins = reliability_bins([(c, h) for c, _, _, h in scored], n_bins)
    murphy = murphy_decomposition([(c, p, a) for c, p, a, _ in scored], n_bins)
    bss_clim = brier_skill_score(brier, brier_clim)
    bss_unif = brier_skill_score(brier, _UNIFORM_BRIER)
    return {
        "n_scored": n,
        "brier": round(brier, 4),
        "log_loss": round(mean_ll, 4),
        "brier_uniform": round(_UNIFORM_BRIER, 4),
        "brier_climatology": round(brier_clim, 4),
        "bss_vs_climatology": round(bss_clim, 4) if bss_clim is not None else None,
        "bss_vs_uniform": round(bss_unif, 4) if bss_unif is not None else None,
        "reliability": bins,
        "ece": expected_calibration_error(bins),
        "murphy": {k: round(v, 4) for k, v in murphy.items()} if murphy else None,
    }
