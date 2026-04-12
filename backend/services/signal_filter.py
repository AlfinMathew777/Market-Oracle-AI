"""Signal quality filter for Market Oracle AI predictions.

Implements hard thresholds that block BUY/SELL output when quality
conditions are not met. No signal should be actionable if confidence,
MC stability, agent consensus, historical accuracy, or catalyst
requirements are below minimum thresholds.

Signal grades (A/B/C/D/F) summarise multi-factor quality for the UI.

Public API (backward-compatible):
  get_recommendation()  — legacy tuple API used by test_core.py
  filter_signal()       — new rich API returning SignalFilterResult
  get_signal_grade()    — compute grade from metrics
  should_output_signal() — boolean gate
  grade_label()         — human-readable grade string
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SignalGrade(str, Enum):
    A_STRONG     = "A"  # High confidence, stable MC, strong consensus
    B_MODERATE   = "B"  # Moderate — tradeable with normal risk management
    C_WEAK       = "C"  # Meets minimum but marginal — monitor only
    D_CONFLICTING = "D" # Mixed or contradictory signals — do not trade
    F_NO_SIGNAL  = "F"  # Below thresholds — no actionable output


class SignalAction(str, Enum):
    """Filtered recommendation — what the user should actually do."""
    BUY   = "BUY"
    SELL  = "SELL"
    HOLD  = "HOLD"   # Insufficient signal — no action
    WAIT  = "WAIT"   # Monitor, but don't trade yet
    AVOID = "AVOID"  # Conflicting signals — stay away


@dataclass(frozen=True)
class SignalThresholds:
    min_confidence: float           = 0.55   # Don't output BUY/SELL below this
    min_confidence_monitor: float   = 0.40   # Below this → HOLD (not even WAIT)
    min_stability: float            = 0.30   # MC direction stability floor (0–1)
    min_agent_consensus: float      = 0.55   # Dominant-side share of total votes
    min_historical_accuracy: float  = 0.40   # System accuracy floor — below = unreliable
    max_confidence_range: float     = 0.20   # If ±range > 20%, signal is uncertain
    require_catalyst: bool          = True   # Block BUY/SELL without a valid trigger


THRESHOLDS = SignalThresholds()


@dataclass
class SignalFilterResult:
    """Rich result from filter_signal() — carries full reasoning for the UI."""
    original_recommendation: str        # What direction alone would produce
    filtered_recommendation: str        # What we actually output (may be HOLD/WAIT)
    signal_grade: SignalGrade
    is_actionable: bool
    block_reasons: list = field(default_factory=list)  # Why signal was blocked
    confidence_original: float = 0.0
    confidence_filtered: float = 0.0
    warnings: list = field(default_factory=list)       # Non-fatal quality notes
    filter_summary: str = ""


def _dominant_consensus(bullish: int, bearish: int, neutral: int) -> float:
    """Return the dominant side's share of all votes (0–1)."""
    total = bullish + bearish + neutral
    if total == 0:
        return 0.0
    dominant = max(bullish, bearish)
    return dominant / total


def should_output_signal(
    confidence: float,
    stability_pct: float,
    bullish: int,
    bearish: int,
    neutral: int,
    confidence_std: Optional[float] = None,
) -> bool:
    """Return True only when the prediction meets ALL quality thresholds.

    Args:
        confidence:       Final confidence value (0–1 scale).
        stability_pct:    MC direction stability as a percentage (0–100).
        bullish/bearish/neutral: Agent vote counts.
        confidence_std:   MC confidence standard deviation (0–100 scale).
                          When provided, a high ± range blocks the signal.
    """
    if confidence < THRESHOLDS.min_confidence:
        logger.debug(
            "Signal blocked: confidence %.1f%% < %.0f%% threshold",
            confidence * 100, THRESHOLDS.min_confidence * 100,
        )
        return False

    if stability_pct / 100 < THRESHOLDS.min_stability:
        logger.debug(
            "Signal blocked: MC stability %.1f%% < %.0f%% threshold",
            stability_pct, THRESHOLDS.min_stability * 100,
        )
        return False

    consensus_ratio = _dominant_consensus(bullish, bearish, neutral)
    if consensus_ratio < THRESHOLDS.min_agent_consensus:
        logger.debug(
            "Signal blocked: agent consensus %.1f%% < %.0f%% threshold",
            consensus_ratio * 100, THRESHOLDS.min_agent_consensus * 100,
        )
        return False

    if confidence_std is not None:
        range_fraction = confidence_std / 100
        if range_fraction > THRESHOLDS.max_confidence_range:
            logger.debug(
                "Signal blocked: confidence range ±%.1f%% > %.0f%% threshold",
                confidence_std, THRESHOLDS.max_confidence_range * 100,
            )
            return False

    return True


def get_signal_grade(
    confidence: float,
    stability_pct: float,
    bullish: int,
    bearish: int,
    neutral: int,
    has_chain_confirmation: bool = False,
) -> SignalGrade:
    """Assign A/B/C/D/F grade based on signal quality factors.

    Args:
        confidence:             Final confidence (0–1).
        stability_pct:          MC direction stability percentage (0–100).
        bullish/bearish/neutral: Vote counts.
        has_chain_confirmation: True when causal chain audit confirmed direction.
    """
    # Grade F — below minimum thresholds
    if not should_output_signal(confidence, stability_pct, bullish, bearish, neutral):
        return SignalGrade.F_NO_SIGNAL

    score = 0

    # Confidence scoring (0–3 pts)
    if confidence >= 0.75:
        score += 3
    elif confidence >= 0.65:
        score += 2
    elif confidence >= 0.55:
        score += 1

    # Stability scoring (0–3 pts)
    stability = stability_pct / 100
    if stability >= 0.70:
        score += 3
    elif stability >= 0.50:
        score += 2
    elif stability >= 0.30:
        score += 1

    # Consensus scoring (0–2 pts)
    consensus = _dominant_consensus(bullish, bearish, neutral)
    if consensus >= 0.75:
        score += 2
    elif consensus >= 0.65:
        score += 1

    # Chain confirmation bonus (0–1 pt)
    if has_chain_confirmation:
        score += 1

    if score >= 7:
        return SignalGrade.A_STRONG
    elif score >= 5:
        return SignalGrade.B_MODERATE
    elif score >= 3:
        return SignalGrade.C_WEAK
    else:
        return SignalGrade.D_CONFLICTING


def filter_signal(
    direction: str,
    confidence: float,
    dominant_stability_pct: float,
    agent_consensus_pct: float,
    historical_accuracy: float = 0.50,
    confidence_range: float = 0.0,
    has_catalyst: bool = True,
    thresholds: SignalThresholds = THRESHOLDS,
) -> SignalFilterResult:
    """Gate a trading signal through all quality thresholds.

    This is the FINAL checkpoint before outputting any BUY/SELL recommendation.
    Call after all confidence calculations, MC simulation, and causal chain audit.

    Args:
        direction:              "bullish" | "bearish" | "neutral" (or UP/DOWN/NEUTRAL)
        confidence:             Final confidence (0–1 scale).
        dominant_stability_pct: Dominant direction win rate (0–100 scale).
                                Must be mc_confidence.dominant_stability_pct — NOT
                                direction_stability_pct, which reads as ~0% for strong
                                bullish signals and would incorrectly block them.
        agent_consensus_pct:    Dominant-side share of total votes (0–1 scale).
        historical_accuracy:    Fraction of past predictions correct (0–1).
                                Pass 0.50 when there is no history yet.
        confidence_range:       MC confidence std-dev as a fraction (0–1).
        has_catalyst:           True when a specific trigger event was identified.
        thresholds:             Override default thresholds for testing.

    Returns:
        SignalFilterResult with filtered recommendation and full reasoning.
    """
    # Convert to 0–1 scale for internal comparisons.
    # dominant_stability_pct is the single source of truth (from MonteCarloConfidence).
    mc_stability = dominant_stability_pct / 100.0

    block_reasons: list = []
    warnings: list = []

    # Normalise direction string
    direction_upper = direction.upper()
    is_bullish = direction_upper in ("UP", "BULLISH")
    is_bearish = direction_upper in ("DOWN", "BEARISH")

    original_rec = (
        SignalAction.BUY.value if is_bullish
        else SignalAction.SELL.value if is_bearish
        else SignalAction.HOLD.value
    )

    # ── Hard blocks ────────────────────────────────────────────────────────────
    # Any one of these entirely prevents an actionable output.

    if mc_stability < thresholds.min_stability:
        block_reasons.append(
            f"MC stability {mc_stability*100:.0f}% < {thresholds.min_stability*100:.0f}% minimum — signal is noise"
        )

    _hist_acc_pct  = round(historical_accuracy * 100, 1)
    _hist_thr_pct  = round(thresholds.min_historical_accuracy * 100, 1)
    if _hist_acc_pct < _hist_thr_pct:
        block_reasons.append(
            f"Historical accuracy {_hist_acc_pct:.0f}% < "
            f"{_hist_thr_pct:.0f}% minimum — system not reliable enough to trade"
        )

    if agent_consensus_pct < thresholds.min_agent_consensus:
        block_reasons.append(
            f"Agent consensus {agent_consensus_pct*100:.0f}% < "
            f"{thresholds.min_agent_consensus*100:.0f}% — no clear directional agreement"
        )

    if confidence_range > thresholds.max_confidence_range:
        block_reasons.append(
            f"Confidence range ±{confidence_range*100:.0f}% exceeds "
            f"±{thresholds.max_confidence_range*100:.0f}% — signal too uncertain"
        )

    if thresholds.require_catalyst and not has_catalyst and (is_bullish or is_bearish):
        block_reasons.append(
            "No catalyst/trigger event identified — avoid directional trade without a clear driver"
        )

    # ── Confidence check ───────────────────────────────────────────────────────
    if block_reasons:
        # Hard block already triggered — force HOLD
        grade = SignalGrade.F_NO_SIGNAL
        filtered_rec = SignalAction.HOLD.value
        is_actionable = False
    elif confidence >= thresholds.min_confidence:
        # Grade signal quality across three dimensions: confidence, MC stability, consensus.
        _score = 0
        if confidence >= 0.75: _score += 3
        elif confidence >= 0.65: _score += 2
        elif confidence >= 0.55: _score += 1
        if mc_stability >= 0.70: _score += 3
        elif mc_stability >= 0.50: _score += 2
        elif mc_stability >= 0.30: _score += 1
        if agent_consensus_pct >= 0.75: _score += 2
        elif agent_consensus_pct >= 0.65: _score += 1
        if _score >= 7: grade = SignalGrade.A_STRONG
        elif _score >= 5: grade = SignalGrade.B_MODERATE
        elif _score >= 3: grade = SignalGrade.C_WEAK
        else: grade = SignalGrade.D_CONFLICTING

        if grade in (SignalGrade.F_NO_SIGNAL, SignalGrade.D_CONFLICTING):
            filtered_rec = SignalAction.AVOID.value
            is_actionable = False
            block_reasons.append("Conflicting quality metrics — do not trade")
        elif grade == SignalGrade.C_WEAK:
            filtered_rec = SignalAction.WAIT.value
            is_actionable = False
            warnings.append("C-grade setup — monitor only, do not trade yet")
        else:
            filtered_rec = original_rec
            is_actionable = original_rec not in (SignalAction.HOLD.value,)
    elif confidence >= thresholds.min_confidence_monitor:
        grade = SignalGrade.C_WEAK
        filtered_rec = SignalAction.WAIT.value
        is_actionable = False
        warnings.append(
            f"Confidence {confidence*100:.0f}% below actionable threshold "
            f"({thresholds.min_confidence*100:.0f}%) — monitoring only"
        )
    else:
        grade = SignalGrade.F_NO_SIGNAL
        filtered_rec = SignalAction.HOLD.value
        is_actionable = False
        block_reasons.append(
            f"Confidence {confidence*100:.0f}% below minimum "
            f"({thresholds.min_confidence_monitor*100:.0f}%)"
        )

    if filtered_rec != original_rec:
        logger.info(
            "Signal filtered %s → %s (grade=%s, conf=%.0f%%, blocks=%d)",
            original_rec, filtered_rec, grade.value, confidence * 100, len(block_reasons),
        )

    summary = (
        f"{grade.value}-grade {filtered_rec} signal — actionable" if is_actionable
        else f"Signal blocked: {block_reasons[0]}" if block_reasons
        else f"Signal downgraded: {warnings[0]}" if warnings
        else "Insufficient signal quality"
    )

    return SignalFilterResult(
        original_recommendation=original_rec,
        filtered_recommendation=filtered_rec,
        signal_grade=grade,
        is_actionable=is_actionable,
        block_reasons=block_reasons,
        confidence_original=confidence,
        confidence_filtered=confidence,
        warnings=warnings,
        filter_summary=summary,
    )


def get_recommendation(
    direction: str,
    confidence: float,
    stability_pct: float,
    bullish: int,
    bearish: int,
    neutral: int,
    confidence_std: Optional[float] = None,
    has_chain_confirmation: bool = False,
) -> tuple[str, SignalGrade, Optional[str]]:
    """Legacy tuple API — delegates to filter_signal() internally.

    Returns (recommendation, grade, reason) for backward compatibility.
    Prefer calling filter_signal() directly for new code.
    """
    consensus = _dominant_consensus(bullish, bearish, neutral)
    result = filter_signal(
        direction=direction,
        confidence=confidence,
        dominant_stability_pct=stability_pct,
        agent_consensus_pct=consensus,
        # No historical accuracy or catalyst at this call site — neutral defaults
        historical_accuracy=0.50,
        confidence_range=(confidence_std / 100) if confidence_std is not None else 0.0,
        has_catalyst=True,  # Don't block on catalyst here — legacy callers don't pass it
    )
    reason = (
        f"SIGNAL_BLOCKED: {'; '.join(result.block_reasons)}" if result.block_reasons
        else result.warnings[0] if result.warnings
        else None
    )
    return result.filtered_recommendation, result.signal_grade, reason


def grade_label(grade: SignalGrade) -> str:
    """Return a human-readable label for the signal grade."""
    return {
        SignalGrade.A_STRONG:      "A — Strong Signal",
        SignalGrade.B_MODERATE:    "B — Moderate Signal",
        SignalGrade.C_WEAK:        "C — Weak Signal (Monitor Only)",
        SignalGrade.D_CONFLICTING: "D — Conflicting Signals",
        SignalGrade.F_NO_SIGNAL:   "F — No Actionable Signal",
    }[grade]
