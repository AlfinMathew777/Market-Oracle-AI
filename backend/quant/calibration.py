"""Monte Carlo confidence calibration.

Catches the case where MC reports 'stable' but the underlying agent consensus
is too weak (< 55%) or the causal chain is critically empty — both of which
indicate the MC bootstrap is amplifying a noisy signal rather than confirming
a real one.

Called once in run_simulation() AFTER the existing is_stable penalty block,
BEFORE the minimum confidence guard.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.game_theory.monte_carlo import MonteCarloConfidence

logger = logging.getLogger(__name__)

# Consensus threshold below which MC stability is unreliable.
# 55% = barely above a coin-flip (50%) — not enough to trust "HIGH" MC conviction.
_WEAK_CONSENSUS_THRESHOLD = 0.55

_PENALTY_WEAK_CONSENSUS  = 0.85   # ×0.85 when stable MC + weak consensus
_PENALTY_EMPTY_CHAIN     = 0.80   # ×0.80 when stable MC + empty causal chain


def calibrate_monte_carlo_confidence(
    final_confidence: float,
    mc_confidence_obj: Optional["MonteCarloConfidence"],
    n_bull: int,
    n_bear: int,
    n_neut: int,
    chain_quality: str,
) -> tuple[float, list[str]]:
    """Apply additional penalty when MC stability is inconsistent with signal quality.

    Args:
        final_confidence:   Current confidence score (0.0–1.0).
        mc_confidence_obj:  Result from run_confidence_monte_carlo(), or None.
        n_bull, n_bear, n_neut: Agent vote counts.
        chain_quality:      "ADEQUATE" | "SPARSE" | "EMPTY" from validate_causal_chain().

    Returns:
        (adjusted_confidence, list_of_audit_strings)
    """
    penalties: list[str] = []
    total = n_bull + n_bear + n_neut

    if total == 0 or mc_confidence_obj is None:
        return final_confidence, penalties

    # Only penalise when MC claims stability — unstable MC already gets ×0.75 elsewhere.
    if not mc_confidence_obj.is_stable:
        return final_confidence, penalties

    consensus_pct = max(n_bull, n_bear) / total

    # Penalty 1: MC says stable but agents barely agree (weak directional signal).
    if consensus_pct < _WEAK_CONSENSUS_THRESHOLD:
        pre = final_confidence
        final_confidence = round(final_confidence * _PENALTY_WEAK_CONSENSUS, 5)
        logger.info(
            "MC calibration: weak consensus (%.0f%%) despite stable MC — "
            "confidence %.1f%% → %.1f%%",
            consensus_pct * 100, pre * 100, final_confidence * 100,
        )
        penalties.append(
            f"MC_CALIBRATION_WEAK_CONSENSUS: "
            f"consensus={consensus_pct:.0%} < {_WEAK_CONSENSUS_THRESHOLD:.0%} "
            f"— ×{_PENALTY_WEAK_CONSENSUS}"
        )

    # Penalty 2: Causal chain is empty — bootstrap stability is meaningless
    # when there is no analytical chain confirming the direction.
    if chain_quality == "EMPTY":
        pre = final_confidence
        final_confidence = round(final_confidence * _PENALTY_EMPTY_CHAIN, 5)
        logger.info(
            "MC calibration: empty causal chain invalidates MC stability — "
            "confidence %.1f%% → %.1f%%",
            pre * 100, final_confidence * 100,
        )
        penalties.append(
            f"MC_CALIBRATION_EMPTY_CHAIN: chain_quality=EMPTY — ×{_PENALTY_EMPTY_CHAIN}"
        )

    return final_confidence, penalties
