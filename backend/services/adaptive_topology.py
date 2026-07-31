"""Adaptive swarm topology — contested-signal agent reallocation.

The persona distribution is already trend-adaptive (get_persona_distribution
weights bulls/bears by trend). This module adds the second adaptive dimension:
when pre-simulation signals CONFLICT with each other, the call is contested —
and a contested call deserves a sharper adversarial debate, not a bigger
neutral bench.

Contest detection (signals available before any agent runs):
  - RSI vs trend conflict   — deeply oversold in a strong downtrend (or deeply
    overbought in a strong uptrend): the documented CONTESTED condition from
    the RSI conflict rule.
  - Alt-data vs trend conflict — the alt-data composite signal points against
    the confirmed price trend.

On a contested call, agents move from the neutral/quant bench to BOTH
directional sides equally (always symmetric — reallocation must never bias
direction, only deepen the debate). Floors keep every persona represented and
the total head-count is always preserved.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Contest score contribution per conflicting signal pair.
_SCORE_PER_CONFLICT = 0.5

# Reallocation tiers: contest score threshold → agents moved to EACH side.
_FULL_CONTEST_THRESHOLD = 0.75      # both signal pairs conflict
_PARTIAL_CONTEST_THRESHOLD = 0.5    # one signal pair conflicts

# Persona floors — no persona is ever emptied by reallocation.
_NEUTRAL_FLOOR = 5
_QUANT_FLOOR = 4

# RSI extremes matching the documented RSI conflict rule.
_RSI_DEEP_OVERSOLD = 25.0
_RSI_DEEP_OVERBOUGHT = 75.0

# Alt-data composite deadband — |signal| below this is noise, not direction.
_ALT_SIGNAL_DEADBAND = 0.05


def compute_contest_score(
    trend_label: str,
    rsi: float | None,
    alt_composite_signal: float | None,
) -> tuple[float, list[str]]:
    """Score how contested the pre-simulation picture is (0.0 → 1.0).

    Args:
        trend_label:          trend bucket from market context (e.g. STRONG_DOWNTREND)
        rsi:                  ticker RSI, or None when unavailable
        alt_composite_signal: alt-data composite in [-1, 1], or None

    Returns:
        (score, reasons) — score in [0, 1]; reasons name each conflict found.
    """
    trend = (trend_label or "").upper()
    score = 0.0
    reasons: list[str] = []

    if rsi is not None:
        rsi_f = float(rsi)
        if rsi_f < _RSI_DEEP_OVERSOLD and "DOWNTREND" in trend:
            score += _SCORE_PER_CONFLICT
            reasons.append(f"RSI {rsi_f:.0f} deeply oversold vs {trend}")
        elif rsi_f > _RSI_DEEP_OVERBOUGHT and "UPTREND" in trend:
            score += _SCORE_PER_CONFLICT
            reasons.append(f"RSI {rsi_f:.0f} deeply overbought vs {trend}")

    if alt_composite_signal is not None:
        sig = float(alt_composite_signal)
        if abs(sig) >= _ALT_SIGNAL_DEADBAND:
            alt_dir = "bullish" if sig > 0 else "bearish"
            if alt_dir == "bullish" and "DOWNTREND" in trend:
                score += _SCORE_PER_CONFLICT
                reasons.append(f"alt-data bullish ({sig:+.2f}) vs {trend}")
            elif alt_dir == "bearish" and "UPTREND" in trend:
                score += _SCORE_PER_CONFLICT
                reasons.append(f"alt-data bearish ({sig:+.2f}) vs {trend}")

    return min(score, 1.0), reasons


def apply_contest_adjustment(
    distribution: dict, contest_score: float
) -> tuple[dict, str]:
    """Return a NEW distribution with agents shifted onto both directional sides.

    Moves come from neutral_fund first, then quant, respecting floors. The move
    is always split evenly between macro_bull and geo_bear — an odd remainder
    is dropped rather than assigned asymmetrically.

    Args:
        distribution:  dict with macro_bull/geo_bear/quant/neutral_fund counts
                       (+ description) as produced by get_persona_distribution
        contest_score: 0.0–1.0 from compute_contest_score

    Returns:
        (new_distribution, note) — note is "" when nothing changed.
    """
    if contest_score >= _FULL_CONTEST_THRESHOLD:
        per_side = 2
    elif contest_score >= _PARTIAL_CONTEST_THRESHOLD:
        per_side = 1
    else:
        return dict(distribution), ""

    wanted = per_side * 2
    neutral_avail = max(0, distribution["neutral_fund"] - _NEUTRAL_FLOOR)
    quant_avail = max(0, distribution["quant"] - _QUANT_FLOOR)

    take_neutral = min(wanted, neutral_avail)
    take_quant = min(wanted - take_neutral, quant_avail)
    taken = take_neutral + take_quant

    # Keep the transfer symmetric: an odd head goes back to its bench.
    if taken % 2 == 1:
        if take_quant > 0:
            take_quant -= 1
        else:
            take_neutral -= 1
        taken -= 1

    if taken == 0:
        return dict(distribution), ""

    adjusted = dict(distribution)
    adjusted["neutral_fund"] -= take_neutral
    adjusted["quant"] -= take_quant
    adjusted["macro_bull"] += taken // 2
    adjusted["geo_bear"] += taken // 2

    note = (
        f"contested signal (score={contest_score:.2f}) — moved {taken} agents "
        f"to the directional debate (+{taken // 2} bull, +{taken // 2} bear)"
    )
    adjusted["description"] = f"{distribution.get('description', '')} | {note}"

    total_before = sum(distribution[k] for k in ("macro_bull", "geo_bear", "quant", "neutral_fund"))
    total_after = sum(adjusted[k] for k in ("macro_bull", "geo_bear", "quant", "neutral_fund"))
    assert total_after == total_before, (
        f"contest adjustment changed head-count: {total_before} → {total_after}"
    )
    return adjusted, note
