"""
Prediction Evaluator
--------------------
Calculates F1, precision, recall, and other metrics for prediction accuracy.
Adapted from NVIDIA NeMo Evaluator concepts — CPU-only.
scikit-learn is optional; falls back to manual calculation if not installed.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

try:
    from sklearn.metrics import (
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available, using manual metric calculation")


@dataclass
class EvaluationResult:
    """Container for F1/precision/recall evaluation metrics."""

    # Overall
    accuracy: float
    f1_macro: float
    f1_weighted: float
    precision_macro: float
    recall_macro: float

    # Per-class
    f1_bullish: float
    f1_bearish: float
    f1_neutral: float
    precision_bullish: float
    precision_bearish: float
    precision_neutral: float
    recall_bullish: float
    recall_bearish: float
    recall_neutral: float

    confusion_matrix: List[List[int]]
    total_predictions: int
    correct_predictions: int

    bullish_total: int
    bullish_correct: int
    bearish_total: int
    bearish_correct: int
    neutral_total: int
    neutral_correct: int

    evaluation_date: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall": {
                "accuracy": round(self.accuracy * 100, 1),
                "f1_macro": round(self.f1_macro, 3),
                "f1_weighted": round(self.f1_weighted, 3),
                "precision_macro": round(self.precision_macro, 3),
                "recall_macro": round(self.recall_macro, 3),
            },
            "per_class": {
                "BULLISH": {
                    "f1": round(self.f1_bullish, 3),
                    "precision": round(self.precision_bullish, 3),
                    "recall": round(self.recall_bullish, 3),
                    "total": self.bullish_total,
                    "correct": self.bullish_correct,
                },
                "BEARISH": {
                    "f1": round(self.f1_bearish, 3),
                    "precision": round(self.precision_bearish, 3),
                    "recall": round(self.recall_bearish, 3),
                    "total": self.bearish_total,
                    "correct": self.bearish_correct,
                },
                "NEUTRAL": {
                    "f1": round(self.f1_neutral, 3),
                    "precision": round(self.precision_neutral, 3),
                    "recall": round(self.recall_neutral, 3),
                    "total": self.neutral_total,
                    "correct": self.neutral_correct,
                },
            },
            "confusion_matrix": self.confusion_matrix,
            "sample_counts": {
                "total": self.total_predictions,
                "correct": self.correct_predictions,
            },
            "evaluation_date": self.evaluation_date,
        }


class PredictionEvaluator:
    """
    Evaluates prediction quality with F1, precision, and recall.

    These metrics handle class imbalance better than simple accuracy,
    which matters because NEUTRAL predictions dominate low-signal periods.
    """

    DIRECTIONS = ["BULLISH", "BEARISH", "NEUTRAL"]

    def evaluate(self, predictions: List[Dict[str, Any]]) -> EvaluationResult:
        """
        Evaluate a list of resolved predictions.

        Args:
            predictions: List of dicts with:
                - predicted_direction: str (BULLISH/BEARISH/NEUTRAL)
                - actual_direction: str (BULLISH/BEARISH/NEUTRAL)

        Returns:
            EvaluationResult with all metrics
        """
        if not predictions:
            return self._empty_result()

        y_pred = [
            p.get("predicted_direction", "NEUTRAL").upper() for p in predictions
        ]
        y_true = [
            p.get("actual_direction", "NEUTRAL").upper() for p in predictions
        ]

        # Clamp to known labels
        y_pred = [d if d in self.DIRECTIONS else "NEUTRAL" for d in y_pred]
        y_true = [d if d in self.DIRECTIONS else "NEUTRAL" for d in y_true]

        if SKLEARN_AVAILABLE:
            return self._sklearn_evaluate(y_true, y_pred)
        return self._manual_evaluate(y_true, y_pred)

    def _sklearn_evaluate(
        self, y_true: List[str], y_pred: List[str]
    ) -> EvaluationResult:
        f1_macro = f1_score(
            y_true, y_pred, labels=self.DIRECTIONS, average="macro", zero_division=0
        )
        f1_weighted = f1_score(
            y_true, y_pred, labels=self.DIRECTIONS, average="weighted", zero_division=0
        )
        precision_macro = precision_score(
            y_true, y_pred, labels=self.DIRECTIONS, average="macro", zero_division=0
        )
        recall_macro = recall_score(
            y_true, y_pred, labels=self.DIRECTIONS, average="macro", zero_division=0
        )
        f1_pc = f1_score(
            y_true, y_pred, labels=self.DIRECTIONS, average=None, zero_division=0
        )
        prec_pc = precision_score(
            y_true, y_pred, labels=self.DIRECTIONS, average=None, zero_division=0
        )
        rec_pc = recall_score(
            y_true, y_pred, labels=self.DIRECTIONS, average=None, zero_division=0
        )
        cm = confusion_matrix(y_true, y_pred, labels=self.DIRECTIONS)
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
        counts = self._count_by_direction(y_true, y_pred)

        return EvaluationResult(
            accuracy=correct / len(y_true),
            f1_macro=float(f1_macro),
            f1_weighted=float(f1_weighted),
            precision_macro=float(precision_macro),
            recall_macro=float(recall_macro),
            f1_bullish=float(f1_pc[0]),
            f1_bearish=float(f1_pc[1]),
            f1_neutral=float(f1_pc[2]),
            precision_bullish=float(prec_pc[0]),
            precision_bearish=float(prec_pc[1]),
            precision_neutral=float(prec_pc[2]),
            recall_bullish=float(rec_pc[0]),
            recall_bearish=float(rec_pc[1]),
            recall_neutral=float(rec_pc[2]),
            confusion_matrix=cm.tolist(),
            total_predictions=len(y_true),
            correct_predictions=correct,
            bullish_total=counts["BULLISH"]["total"],
            bullish_correct=counts["BULLISH"]["correct"],
            bearish_total=counts["BEARISH"]["total"],
            bearish_correct=counts["BEARISH"]["correct"],
            neutral_total=counts["NEUTRAL"]["total"],
            neutral_correct=counts["NEUTRAL"]["correct"],
            evaluation_date=datetime.now(timezone.utc).isoformat(),
        )

    def _manual_evaluate(
        self, y_true: List[str], y_pred: List[str]
    ) -> EvaluationResult:
        """Manual F1 calculation — used when sklearn is unavailable."""
        counts = self._count_by_direction(y_true, y_pred)
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)

        def _f1(direction: str):
            tp = counts[direction]["correct"]
            pred_total = sum(1 for p in y_pred if p == direction)
            act_total = counts[direction]["total"]
            prec = tp / pred_total if pred_total > 0 else 0.0
            rec = tp / act_total if act_total > 0 else 0.0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            return f1, prec, rec

        f1_b, p_b, r_b = _f1("BULLISH")
        f1_br, p_br, r_br = _f1("BEARISH")
        f1_n, p_n, r_n = _f1("NEUTRAL")
        f1_macro = (f1_b + f1_br + f1_n) / 3
        prec_macro = (p_b + p_br + p_n) / 3
        rec_macro = (r_b + r_br + r_n) / 3

        dir_idx = {"BULLISH": 0, "BEARISH": 1, "NEUTRAL": 2}
        cm = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
        for t, p in zip(y_true, y_pred):
            cm[dir_idx[t]][dir_idx[p]] += 1

        return EvaluationResult(
            accuracy=correct / len(y_true) if y_true else 0,
            f1_macro=f1_macro,
            f1_weighted=f1_macro,  # Simplified when sklearn unavailable
            precision_macro=prec_macro,
            recall_macro=rec_macro,
            f1_bullish=f1_b, f1_bearish=f1_br, f1_neutral=f1_n,
            precision_bullish=p_b, precision_bearish=p_br, precision_neutral=p_n,
            recall_bullish=r_b, recall_bearish=r_br, recall_neutral=r_n,
            confusion_matrix=cm,
            total_predictions=len(y_true),
            correct_predictions=correct,
            bullish_total=counts["BULLISH"]["total"],
            bullish_correct=counts["BULLISH"]["correct"],
            bearish_total=counts["BEARISH"]["total"],
            bearish_correct=counts["BEARISH"]["correct"],
            neutral_total=counts["NEUTRAL"]["total"],
            neutral_correct=counts["NEUTRAL"]["correct"],
            evaluation_date=datetime.now(timezone.utc).isoformat(),
        )

    def _count_by_direction(
        self, y_true: List[str], y_pred: List[str]
    ) -> Dict[str, Dict[str, int]]:
        counts: Dict[str, Dict[str, int]] = {
            d: {"total": 0, "correct": 0} for d in self.DIRECTIONS
        }
        for true, pred in zip(y_true, y_pred):
            if true in counts:
                counts[true]["total"] += 1
                if true == pred:
                    counts[true]["correct"] += 1
        return counts

    def _empty_result(self) -> EvaluationResult:
        return EvaluationResult(
            accuracy=0, f1_macro=0, f1_weighted=0, precision_macro=0, recall_macro=0,
            f1_bullish=0, f1_bearish=0, f1_neutral=0,
            precision_bullish=0, precision_bearish=0, precision_neutral=0,
            recall_bullish=0, recall_bearish=0, recall_neutral=0,
            confusion_matrix=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            total_predictions=0, correct_predictions=0,
            bullish_total=0, bullish_correct=0,
            bearish_total=0, bearish_correct=0,
            neutral_total=0, neutral_correct=0,
            evaluation_date=datetime.now(timezone.utc).isoformat(),
        )


def evaluate_predictions(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluate predictions and return metrics dict."""
    return PredictionEvaluator().evaluate(predictions).to_dict()
