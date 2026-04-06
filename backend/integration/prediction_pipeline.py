"""Prediction pipeline integration bridge — merges quant engine with agent consensus.

SAFETY CONTRACT
───────────────
This function is OPTIONAL in the existing pipeline. It wraps every operation in
try/except so that quant engine errors NEVER crash the existing agent simulation.
If anything fails, the original agent_consensus dict is returned unchanged.

Source weights
──────────────
  Quant engine   55 %  (factor model + vol model + GBM Monte Carlo)
  Agent swarm    35 %  (50-agent LLM consensus — the existing pipeline)
  OSINT signals  10 %  (WorldMonitor globe / chokepoint data)

If OSINT is absent, its 10 % is redistributed to agents (total agent weight = 45 %).
If quant is absent, returns agent consensus unchanged — the UI shows a subtle note.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_QUANT_WEIGHT = 0.55
_AGENT_WEIGHT = 0.35
_OSINT_WEIGHT = 0.10

# Hard cap on merged confidence — matches the existing pipeline cap in test_core.py
_MAX_CONFIDENCE = 0.85

_DIR_TO_SCORE = {"UP": 1.0, "BULLISH": 1.0, "NEUTRAL": 0.0, "DOWN": -1.0, "BEARISH": -1.0}


def merge_predictions(
    quant_result: Optional[dict],
    agent_consensus: dict,
    osint_signals: Optional[dict] = None,
) -> dict:
    """Merge quant, agent, and OSINT signals into a single weighted prediction.

    Args:
        quant_result:    Output from QuantEngine.prediction() — None if unavailable.
                         Expected keys: direction, quant_confidence, vol_regime,
                                        var_95, cvar_95, technical_score.
        agent_consensus: Existing agent output dict. Must have keys:
                         direction ("UP"/"DOWN"/"NEUTRAL"), confidence (0–1).
                         All other keys are passed through unchanged.
        osint_signals:   Optional dict with keys: direction, score (0–1).
                         Pass None if OSINT data is unavailable.

    Returns:
        Merged dict. Includes all original agent_consensus keys plus:
          - direction          (may differ from agent-only direction)
          - confidence         (weighted blend, capped at 0.85)
          - prediction_sources (quant/agents/osint weight breakdown)
          - quant_vol_regime   (LOW / NORMAL / HIGH / EXTREME — or None)
          - quant_var_95       (1-day VaR at 95% confidence — or None)
          - quant_unavailable  (True when quant engine was skipped)
    """
    try:
        # ── Graceful degradation ─────────────────────────────────────────────
        if not quant_result or quant_result.get("status") == "error":
            logger.info(
                "Quant engine output absent/errored — returning agent consensus unchanged"
            )
            return {
                **agent_consensus,
                "prediction_sources": {
                    "quant_pct": 0,
                    "agents_pct": 100,
                    "osint_pct": 0,
                },
                "quant_unavailable": True,
                "quant_vol_regime": None,
                "quant_var_95": None,
            }

        # ── Normalise directions to scalar scores ────────────────────────────
        def _score(direction: str, confidence: float) -> float:
            return _DIR_TO_SCORE.get(direction.upper(), 0.0) * max(0.0, min(1.0, confidence))

        quant_score = _score(
            quant_result.get("direction", "NEUTRAL"),
            quant_result.get("quant_confidence", 0.5),
        )
        agent_score = _score(
            agent_consensus.get("direction", "NEUTRAL"),
            agent_consensus.get("confidence", 0.5),
        )

        # ── Determine effective weights ──────────────────────────────────────
        if osint_signals and osint_signals.get("direction"):
            osint_score = _score(
                osint_signals["direction"],
                osint_signals.get("score", 0.5),
            )
            q_w, a_w, o_w = _QUANT_WEIGHT, _AGENT_WEIGHT, _OSINT_WEIGHT
        else:
            osint_score = 0.0
            # Redistribute OSINT weight to agents
            q_w = _QUANT_WEIGHT
            a_w = _AGENT_WEIGHT + _OSINT_WEIGHT
            o_w = 0.0

        # ── Weighted blend ───────────────────────────────────────────────────
        weighted_score = quant_score * q_w + agent_score * a_w + osint_score * o_w

        if weighted_score > 0.05:
            merged_direction = "UP"
        elif weighted_score < -0.05:
            merged_direction = "DOWN"
        else:
            merged_direction = "NEUTRAL"

        merged_confidence = min(_MAX_CONFIDENCE, abs(weighted_score))

        return {
            # Pass through all original agent fields unchanged
            **agent_consensus,
            # Override direction and confidence with merged values
            "direction": merged_direction,
            "confidence": round(merged_confidence, 3),
            # Provenance metadata
            "prediction_sources": {
                "quant_pct": round(q_w * 100),
                "agents_pct": round(a_w * 100),
                "osint_pct": round(o_w * 100),
            },
            "quant_unavailable": False,
            "quant_vol_regime": quant_result.get("vol_regime"),
            "quant_var_95": quant_result.get("var_95"),
            "quant_cvar_95": quant_result.get("cvar_95"),
            "quant_technical_score": quant_result.get("technical_score"),
            "quant_technical_signal": quant_result.get("technical_signal"),
        }

    except Exception as e:
        # CRITICAL: this must NEVER propagate — the main pipeline depends on it
        logger.error("merge_predictions failed (non-fatal, returning agent consensus): %s", e, exc_info=True)
        return agent_consensus
