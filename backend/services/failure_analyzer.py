"""
Failure Pattern Analyzer — Data Flywheel
-----------------------------------------
Analyzes why predictions fail and generates actionable recommendations.
Implements the "data flywheel": learn from failures → improve prompts/weights.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FailurePattern(str, Enum):
    """Categories of prediction failures."""

    MISSED_CATALYST = "missed_catalyst"
    WRONG_DIRECTION = "wrong_direction"
    TIMING_OFF = "timing_off"
    EXTERNAL_SHOCK = "external_shock"
    OVERCONFIDENCE = "overconfidence"
    UNDERCONFIDENCE = "underconfidence"
    SECTOR_MISMATCH = "sector_mismatch"
    SIGNAL_IGNORED = "signal_ignored"
    CONSENSUS_WRONG = "consensus_wrong"
    TECHNICAL_FAILURE = "technical_failure"


@dataclass
class FailureAnalysis:
    """Analysis of a single failed prediction."""

    prediction_id: str
    ticker: str
    predicted_direction: str
    actual_direction: str
    confidence: float
    pattern: FailurePattern
    contributing_factors: List[str]
    missed_signals: List[str]
    recommendation: str


@dataclass
class FlywheelReport:
    """Aggregated failure analysis with actionable recommendations."""

    total_analyzed: int
    total_failures: int
    failure_rate: float
    pattern_counts: Dict[str, int]
    pattern_percentages: Dict[str, float]
    top_patterns: List[str]
    most_affected_tickers: List[str]
    prompt_recommendations: List[str]
    weight_adjustments: Dict[str, float]
    analysis_period: str
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "total_analyzed": self.total_analyzed,
                "total_failures": self.total_failures,
                "failure_rate": round(self.failure_rate * 100, 1),
            },
            "patterns": {
                "counts": self.pattern_counts,
                "percentages": {k: round(v * 100, 1) for k, v in self.pattern_percentages.items()},
            },
            "top_issues": {
                "patterns": self.top_patterns,
                "tickers": self.most_affected_tickers,
            },
            "recommendations": {
                "prompt_changes": self.prompt_recommendations,
                "weight_adjustments": self.weight_adjustments,
            },
            "metadata": {
                "period": self.analysis_period,
                "generated": self.generated_at,
            },
        }


_PATTERN_RECOMMENDATIONS: Dict[FailurePattern, List[str]] = {
    FailurePattern.MISSED_CATALYST: [
        "Increase weight on recent news signals (last 24h)",
        "Add news recency scoring to trigger analysis",
    ],
    FailurePattern.WRONG_DIRECTION: [
        "Require stronger agent consensus (>60%) before directional call",
        "Add contrarian signal check when sentiment is extreme",
    ],
    FailurePattern.TIMING_OFF: [
        "Adjust prediction horizon based on event type",
        "Add momentum indicators to timing analysis",
    ],
    FailurePattern.EXTERNAL_SHOCK: [
        "External shocks are inherently unpredictable — acceptable failure mode",
        "Consider adding geopolitical risk monitoring to improve early detection",
    ],
    FailurePattern.OVERCONFIDENCE: [
        "Cap confidence at 70% when agent consensus < 65%",
        "Add confidence calibration from historical accuracy by category",
    ],
    FailurePattern.UNDERCONFIDENCE: [
        "Increase confidence when multiple strong signals align",
        "Review signal strength thresholds for directional calls",
    ],
    FailurePattern.SECTOR_MISMATCH: [
        "Verify sector classifier coverage for all tickers",
        "Add missing tickers to sector configuration",
    ],
    FailurePattern.SIGNAL_IGNORED: [
        "Review signal filtering logic in sector prompts",
        "Ensure key signals are not blocked by sector blocklist",
    ],
    FailurePattern.CONSENSUS_WRONG: [
        "Add agent diversity scoring to detect herding",
        "Weight agents by historical accuracy per category",
    ],
    FailurePattern.TECHNICAL_FAILURE: [
        "Review API timeouts and fallback logic",
        "Add data quality validation before simulation",
    ],
}

_SHOCK_KEYWORDS = frozenset([
    "shock", "unexpected", "surprise", "breaking", "emergency",
    "black swan", "sudden", "unprecedented",
])


class FailureAnalyzer:
    """
    Analyzes prediction failures to drive continuous improvement.

    Data flywheel:
    1. Collect failed predictions
    2. Categorize failure patterns
    3. Generate actionable recommendations
    4. Recommendations feed back to improve prompts/weights
    """

    def analyze_failure(
        self,
        prediction: Dict[str, Any],
        market_data: Optional[Dict[str, Any]] = None,
    ) -> FailureAnalysis:
        """
        Analyze a single failed prediction.

        Args:
            prediction: Failed prediction dict with metadata
            market_data: Market conditions at prediction time (optional)

        Returns:
            FailureAnalysis with identified pattern and recommendation
        """
        ticker = prediction.get("ticker", "UNKNOWN")
        predicted = prediction.get("predicted_direction", "NEUTRAL").upper()
        actual = prediction.get("actual_direction", "NEUTRAL").upper()
        confidence = float(prediction.get("confidence", 50))

        pattern, factors, missed = self._categorize_failure(
            prediction, predicted, actual, confidence
        )
        recs = _PATTERN_RECOMMENDATIONS.get(pattern, [])
        recommendation = recs[0] if recs else "Review prediction logic"

        return FailureAnalysis(
            prediction_id=prediction.get("id", "unknown"),
            ticker=ticker,
            predicted_direction=predicted,
            actual_direction=actual,
            confidence=confidence,
            pattern=pattern,
            contributing_factors=factors,
            missed_signals=missed,
            recommendation=recommendation,
        )

    def _categorize_failure(
        self,
        prediction: Dict,
        predicted: str,
        actual: str,
        confidence: float,
    ) -> Tuple[FailurePattern, List[str], List[str]]:
        """Categorize the failure into a pattern."""

        # High-confidence wrong direction → overconfidence or wrong direction
        if confidence > 70 and predicted != actual:
            if (predicted == "BULLISH" and actual == "BEARISH") or (
                predicted == "BEARISH" and actual == "BULLISH"
            ):
                return FailurePattern.WRONG_DIRECTION, ["High confidence but opposite outcome"], []
            return FailurePattern.OVERCONFIDENCE, ["High confidence but wrong direction"], []

        # Predicted NEUTRAL but price moved
        if predicted == "NEUTRAL" and actual in ("BULLISH", "BEARISH"):
            if confidence < 40:
                return FailurePattern.UNDERCONFIDENCE, ["Missed directional move at low confidence"], []
            return FailurePattern.MISSED_CATALYST, ["Failed to identify catalyst"], []

        # Complete direction flip
        if (predicted == "BULLISH" and actual == "BEARISH") or (
            predicted == "BEARISH" and actual == "BULLISH"
        ):
            agent_votes = prediction.get("agent_votes", {})
            n_bull = agent_votes.get("bullish", 0)
            n_bear = agent_votes.get("bearish", 0)
            if abs(n_bull - n_bear) < 5:
                return FailurePattern.CONSENSUS_WRONG, ["Split consensus led to wrong call"], []
            return FailurePattern.WRONG_DIRECTION, ["Directional analysis failed"], []

        # Check for external shock markers
        causal_chain = prediction.get("causal_chain", {})
        trigger = (causal_chain.get("trigger_event") or causal_chain.get("summary") or "").lower()
        if any(kw in trigger for kw in _SHOCK_KEYWORDS):
            return FailurePattern.EXTERNAL_SHOCK, ["Unpredictable external event"], []

        return FailurePattern.MISSED_CATALYST, ["Unknown failure cause"], []

    def generate_flywheel_report(
        self,
        predictions: List[Dict[str, Any]],
        days: int = 30,
    ) -> FlywheelReport:
        """
        Generate a comprehensive failure analysis report.

        Args:
            predictions: All predictions (both correct and incorrect).
                         Each dict must have a `was_correct` bool field.
            days: Analysis period in days (used only for the label)

        Returns:
            FlywheelReport with patterns and actionable recommendations
        """
        failures = [p for p in predictions if not p.get("was_correct", True)]

        if not failures:
            return FlywheelReport(
                total_analyzed=len(predictions),
                total_failures=0,
                failure_rate=0.0,
                pattern_counts={},
                pattern_percentages={},
                top_patterns=[],
                most_affected_tickers=[],
                prompt_recommendations=["No failures to analyze — system performing well"],
                weight_adjustments={},
                analysis_period=f"Last {days} days",
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        pattern_counts: Dict[str, int] = defaultdict(int)
        ticker_failures: Dict[str, int] = defaultdict(int)

        for failure in failures:
            analysis = self.analyze_failure(failure)
            pattern_counts[analysis.pattern.value] += 1
            ticker_failures[analysis.ticker] += 1

        total_failures = len(failures)
        pattern_percentages = {k: v / total_failures for k, v in pattern_counts.items()}

        top_patterns = [
            p for p, _ in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        ]
        most_affected = [
            t for t, _ in sorted(ticker_failures.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        recommendations: List[str] = []
        weight_adjustments: Dict[str, float] = {}

        for pattern_name in top_patterns:
            pattern = FailurePattern(pattern_name)
            recommendations.extend(_PATTERN_RECOMMENDATIONS.get(pattern, []))
            if pattern == FailurePattern.MISSED_CATALYST:
                weight_adjustments["news_recency"] = 1.3
            elif pattern == FailurePattern.WRONG_DIRECTION:
                weight_adjustments["consensus_threshold"] = 0.65
            elif pattern == FailurePattern.OVERCONFIDENCE:
                weight_adjustments["confidence_cap"] = 0.70

        # Deduplicate while preserving order
        seen: set = set()
        deduped: List[str] = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                deduped.append(rec)

        return FlywheelReport(
            total_analyzed=len(predictions),
            total_failures=total_failures,
            failure_rate=total_failures / len(predictions) if predictions else 0.0,
            pattern_counts=dict(pattern_counts),
            pattern_percentages=dict(pattern_percentages),
            top_patterns=top_patterns,
            most_affected_tickers=most_affected,
            prompt_recommendations=deduped[:5],
            weight_adjustments=weight_adjustments,
            analysis_period=f"Last {days} days",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


def analyze_failures(predictions: List[Dict[str, Any]], days: int = 30) -> Dict[str, Any]:
    """Generate failure analysis report as JSON-ready dict."""
    return FailureAnalyzer().generate_flywheel_report(predictions, days).to_dict()
