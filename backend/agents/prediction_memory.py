"""
Prediction Memory System
------------------------
Learns from past Reasoning Synthesizer predictions to improve future reasoning.
Provides historical context that gets injected into the LLM prompt.
"""

import logging
from typing import Any, Optional

from database import (
    get_reasoning_predictions_for_memory,
    get_reasoning_accuracy_stats,
    get_full_prediction_log,
)

logger = logging.getLogger(__name__)

# Prompt template injected into the Reasoning Synthesizer when memory is available
MEMORY_PROMPT_TEMPLATE = """
## HISTORICAL MEMORY CONTEXT

{memory_summary}

**Similar past predictions for {ticker} ({direction}):**
{similar_summary}

**Causal chain effectiveness for these domains:**
- Historical accuracy: {causal_accuracy}%
- Effectiveness rating: {effectiveness}
- Sample size: {sample_size} predictions

**Confidence calibration note:**
{calibration_note}

Use this context to calibrate your prediction. If similar predictions have failed,
explain why this case might be different.
"""


class PredictionMemory:
    """
    Provides historical context to the Reasoning Synthesizer.

    Key functions:
    1. Retrieve similar past predictions for the same ticker/direction
    2. Estimate causal chain effectiveness from domain overlap
    3. Suggest confidence adjustments based on historical calibration
    4. Generate a prompt snippet for injection into LLM context
    """

    async def get_memory_context(
        self,
        stock_ticker: str,
        event_domains: list[str],
        direction: str,
        stated_confidence: int,
    ) -> dict[str, Any]:
        """
        Build complete memory context for the Reasoning Synthesizer.

        Returns a dict with structured data AND a `memory_prompt` string
        ready for prompt injection.
        """
        similar = await get_reasoning_predictions_for_memory(
            ticker=stock_ticker, direction=direction, days=180, limit=10
        )

        # When Reasoning Synthesizer has no history, fall back to the main
        # prediction_log table so the memory context reflects actual track record.
        if not similar:
            similar = await self._prediction_log_as_memory(stock_ticker, direction)

        # Filter by domain overlap if event_classification data is present
        domain_matched = []
        for pred in similar:
            ec = pred.get("event_classification")
            if isinstance(ec, dict):
                overlap = set(event_domains) & set(ec.get("domains", []))
                if overlap:
                    pred = dict(pred)
                    pred["domain_overlap"] = list(overlap)
                    domain_matched.append(pred)
            else:
                domain_matched.append(pred)

        similar_to_use = domain_matched[:5] if domain_matched else similar[:5]

        causal_stats = await self._causal_effectiveness(stock_ticker, direction)
        calibration = await self._confidence_calibration(stock_ticker, direction, stated_confidence)

        prompt = self._build_prompt(
            ticker=stock_ticker,
            direction=direction,
            similar=similar_to_use,
            causal_stats=causal_stats,
            calibration=calibration,
        )

        return {
            "has_memory": bool(similar_to_use),
            "similar_predictions": [
                {
                    "outcome": p["outcome_status"],
                    "return_pct": p.get("actual_return_pct"),
                    "confidence": p["confidence_score"],
                }
                for p in similar_to_use
            ],
            "causal_chain_effectiveness": causal_stats,
            "confidence_calibration": calibration,
            "memory_prompt": prompt,
        }

    # ── private helpers ────────────────────────────────────────────────────────

    async def _prediction_log_as_memory(
        self, ticker: str, direction: str
    ) -> list[dict[str, Any]]:
        """
        Return main simulation prediction_log entries shaped to match the
        reasoning_predictions memory format when reasoning_predictions is empty.

        This prevents the memory context from claiming "first prediction" when
        the main simulation has an existing track record.
        """
        _dir_map = {
            "bullish": "bullish", "up": "bullish",
            "bearish": "bearish", "down": "bearish",
            "neutral": "neutral",
        }
        target_dir = _dir_map.get(direction.lower(), direction.lower())

        try:
            entries = await get_full_prediction_log(ticker=ticker, days=180, limit=10)
        except Exception as e:
            logger.warning("_prediction_log_as_memory failed: %s", e)
            return []

        result: list[dict[str, Any]] = []
        for entry in entries:
            pred_dir = entry.get("predicted_direction", "").lower()
            if pred_dir != target_dir:
                continue
            correct = entry.get("prediction_correct")
            outcome = (
                "CORRECT"   if correct is not None and correct >= 0.5
                else "INCORRECT" if correct is not None
                else "PENDING"
            )
            result.append({
                "outcome_status":       outcome,
                "actual_return_pct":    None,
                "confidence_score":     round(float(entry.get("confidence", 0.5)) * 100),
                "event_classification": None,
                "_source":              "prediction_log",
            })
        if result:
            logger.info(
                "Memory fallback: %d prediction_log entries for %s %s",
                len(result), ticker, direction,
            )
        return result

    async def _causal_effectiveness(self, ticker: str, direction: str) -> dict[str, Any]:
        """Estimate effectiveness of causal chains for this ticker/direction."""
        stats = await get_reasoning_accuracy_stats(ticker=ticker, direction=direction, days=180)
        sample = stats.get("resolved_predictions", 0)
        accuracy = stats.get("accuracy_pct", 0.0)

        if sample < 3:
            return {
                "sample_size": sample,
                "accuracy_pct": 0.0,
                "effectiveness": "UNKNOWN",
                "note": "Insufficient historical data",
            }

        effectiveness = "HIGH" if accuracy >= 65 else "MEDIUM" if accuracy >= 50 else "LOW"
        return {
            "sample_size": sample,
            "accuracy_pct": accuracy,
            "effectiveness": effectiveness,
            "note": f"Based on {sample} resolved predictions",
        }

    async def _confidence_calibration(
        self, ticker: str, direction: str, stated_confidence: int
    ) -> dict[str, Any]:
        """Compare stated confidence to historical accuracy for calibration guidance."""
        stats = await get_reasoning_accuracy_stats(ticker=ticker, direction=direction, days=180)
        sample = stats.get("resolved_predictions", 0)

        if sample < 5:
            return {
                "adjustment": 0,
                "adjusted_confidence": stated_confidence,
                "reason": "Insufficient data for calibration",
            }

        actual_accuracy = stats.get("accuracy_pct", 0.0)
        avg_confidence = stats.get("avg_confidence", stated_confidence)
        gap = avg_confidence - actual_accuracy

        if gap > 15:
            adjustment = -min(15, int(gap / 2))
        elif gap < -15:
            adjustment = min(15, int(abs(gap) / 2))
        else:
            adjustment = 0

        return {
            "historical_accuracy": round(actual_accuracy, 2),
            "avg_stated_confidence": round(avg_confidence, 2),
            "calibration_gap": round(gap, 2),
            "adjustment": adjustment,
            "adjusted_confidence": max(0, min(100, stated_confidence + adjustment)),
            "reason": f"Historical accuracy {actual_accuracy:.0f}% vs stated {avg_confidence:.0f}%",
            "sample_size": sample,
        }

    def _build_prompt(
        self,
        ticker: str,
        direction: str,
        similar: list[dict[str, Any]],
        causal_stats: dict[str, Any],
        calibration: dict[str, Any],
    ) -> str:
        """Render the memory context as a prompt string for LLM injection."""
        if not similar and causal_stats.get("effectiveness") == "UNKNOWN":
            return ""

        # Similar predictions summary
        if similar:
            correct = sum(1 for p in similar if p["outcome_status"] == "CORRECT")
            similar_summary = (
                f"{len(similar)} similar predictions found: {correct} correct, "
                f"{len(similar) - correct} incorrect/other."
            )
        else:
            similar_summary = "No similar past predictions found."

        # Memory headline
        if similar:
            correct = sum(1 for p in similar if p["outcome_status"] == "CORRECT")
            accuracy = correct / len(similar) * 100
            memory_summary = f"Past accuracy for {ticker} {direction}: {accuracy:.0f}% ({correct}/{len(similar)} correct)"
        else:
            memory_summary = f"No historical predictions found for {ticker} {direction}"

        # Calibration note
        adj = calibration.get("adjustment", 0)
        if adj != 0:
            calibration_note = (
                f"Suggest adjusting confidence by {adj:+d} points. "
                f"{calibration.get('reason', '')}"
            )
        else:
            calibration_note = "Confidence appears well-calibrated based on history."

        return MEMORY_PROMPT_TEMPLATE.format(
            ticker=ticker,
            direction=direction,
            memory_summary=memory_summary,
            similar_summary=similar_summary,
            causal_accuracy=causal_stats.get("accuracy_pct", 0.0),
            effectiveness=causal_stats.get("effectiveness", "UNKNOWN"),
            sample_size=causal_stats.get("sample_size", 0),
            calibration_note=calibration_note,
        ).strip()
