"""ML-based anomaly detection for Market Oracle AI signal quality.

Uses scikit-learn's IsolationForest to detect unusual prediction patterns
that may indicate:
  - Hallucinated or erratic signals
  - Systematic bias in a particular direction
  - Unusual confidence distribution
  - Data feed contamination

Feature vector (7 dimensions per prediction window):
  1. mean_confidence     — average confidence in the window
  2. confidence_stddev   — spread of confidence scores
  3. bull_ratio          — fraction of bullish signals
  4. bear_ratio          — fraction of bearish signals
  5. neutral_ratio       — fraction of neutral signals
  6. accuracy_rate       — fraction of resolved predictions that were correct
  7. avg_execution_time  — mean simulation wall-clock time (in seconds)

The model is trained on the last N_TRAIN predictions (rolling window) and
predicts anomalies on the latest WINDOW_SIZE predictions.

Usage:
    from monitoring.anomaly_detector import AnomalyDetector, check_ml_anomaly

    # One-shot check (used by alerts.py)
    result = await check_ml_anomaly()
    # result: {"anomaly": True/False, "score": -0.12, "reason": "..."} | None

    # Re-train the model on fresh data
    detector = AnomalyDetector()
    await detector.train()
    result = await detector.predict()
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Hyperparameters ───────────────────────────────────────────────────────────

N_TRAIN       = 200     # predictions used to build the normal profile
WINDOW_SIZE   = 10      # most-recent predictions evaluated for anomaly
CONTAMINATION = 0.05    # expected fraction of anomalies in training data (5%)
MIN_SAMPLES   = 30      # minimum resolved predictions needed to train


class AnomalyDetector:
    """
    Rolling IsolationForest detector.

    Lifecycle:
        detector = AnomalyDetector()
        await detector.train()             # fits on historical data
        result = await detector.predict()  # scores the latest window
    """

    def __init__(self):
        self._model = None       # sklearn IsolationForest (fitted)
        self._trained_at: Optional[datetime] = None

    # ── Feature extraction ────────────────────────────────────────────────────

    @staticmethod
    def _extract_features(rows: list) -> Optional[np.ndarray]:
        """
        Build a (1, 7) feature vector from a list of prediction_log rows.
        Returns None if there are not enough resolved predictions.
        """
        if not rows:
            return None

        confidences = [float(r.get("confidence") or 0) for r in rows]
        directions  = [str(r.get("predicted_direction") or "").lower() for r in rows]
        correct     = [r.get("prediction_correct") for r in rows if r.get("prediction_correct") is not None]

        n = len(rows)
        bull_n    = sum(1 for d in directions if d == "bullish")
        bear_n    = sum(1 for d in directions if d == "bearish")
        neut_n    = sum(1 for d in directions if d == "neutral")
        acc_rate  = (sum(correct) / len(correct)) if correct else 0.0

        # execution_time may be absent from prediction_log rows — default to 0
        exec_times = [float(r.get("execution_time") or 0) for r in rows]

        mean_conf   = float(np.mean(confidences)) if confidences else 0.0
        std_conf    = float(np.std(confidences))  if confidences else 0.0

        features = np.array([[
            mean_conf,
            std_conf,
            bull_n / n,
            bear_n / n,
            neut_n / n,
            acc_rate,
            float(np.mean(exec_times)) if exec_times else 0.0,
        ]], dtype=np.float64)

        return features

    # ── Training ──────────────────────────────────────────────────────────────

    async def train(self) -> bool:
        """
        Fetch the last N_TRAIN predictions and fit the IsolationForest.
        Returns True on success, False if insufficient data.
        """
        rows = await _fetch_recent_predictions(N_TRAIN)
        if len(rows) < MIN_SAMPLES:
            logger.info(
                "AnomalyDetector: not enough data to train (%d < %d)",
                len(rows), MIN_SAMPLES,
            )
            return False

        # Build per-window feature matrix for training
        # Use a sliding window of WINDOW_SIZE across the N_TRAIN rows
        X_rows = []
        for i in range(len(rows) - WINDOW_SIZE + 1):
            window = rows[i: i + WINDOW_SIZE]
            features = self._extract_features(window)
            if features is not None:
                X_rows.append(features[0])

        if len(X_rows) < 10:
            logger.info("AnomalyDetector: not enough windows to train (%d)", len(X_rows))
            return False

        X = np.array(X_rows, dtype=np.float64)

        try:
            from sklearn.ensemble import IsolationForest
            model = IsolationForest(
                n_estimators=100,
                contamination=CONTAMINATION,
                random_state=42,
                n_jobs=1,
            )
            model.fit(X)
            self._model = model
            self._trained_at = datetime.now(timezone.utc)
            logger.info(
                "AnomalyDetector trained on %d windows from %d predictions",
                len(X_rows), len(rows),
            )
            return True
        except Exception as exc:
            logger.error("AnomalyDetector training failed: %s", exc)
            return False

    # ── Prediction ────────────────────────────────────────────────────────────

    async def predict(self) -> Optional[dict]:
        """
        Score the most recent WINDOW_SIZE predictions.

        Returns:
            {
                "anomaly": True/False,
                "score": float,          # IsolationForest anomaly score (negative = more anomalous)
                "reason": str,           # human-readable description
                "features": dict,        # extracted feature values
                "trained_at": str,       # ISO timestamp of last training
            }
            or None if the model is not fitted or data is insufficient.
        """
        if self._model is None:
            return None

        rows = await _fetch_recent_predictions(WINDOW_SIZE)
        if len(rows) < WINDOW_SIZE:
            return None

        features = self._extract_features(rows)
        if features is None:
            return None

        score = float(self._model.decision_function(features)[0])
        label = int(self._model.predict(features)[0])   # -1 = anomaly, 1 = normal
        is_anomaly = label == -1

        feature_names = [
            "mean_confidence", "confidence_stddev",
            "bull_ratio", "bear_ratio", "neutral_ratio",
            "accuracy_rate", "avg_execution_time",
        ]
        feature_dict = dict(zip(feature_names, features[0].tolist()))

        reason = _build_reason(is_anomaly, score, feature_dict)

        return {
            "anomaly": is_anomaly,
            "score": round(score, 4),
            "reason": reason,
            "features": {k: round(v, 4) for k, v in feature_dict.items()},
            "trained_at": self._trained_at.isoformat() if self._trained_at else None,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_detector = AnomalyDetector()
_last_trained: Optional[datetime] = None
_RETRAIN_INTERVAL = timedelta(hours=6)   # re-train every 6 hours


async def check_ml_anomaly() -> Optional[dict]:
    """
    Convenience function for alerts.py. Trains if necessary, then predicts.

    Returns the anomaly result dict, or None if there's not enough data.
    """
    global _last_trained

    now = datetime.now(timezone.utc)
    needs_train = (
        _last_trained is None
        or (now - _last_trained) > _RETRAIN_INTERVAL
        or _detector._model is None
    )

    if needs_train:
        trained = await _detector.train()
        if trained:
            _last_trained = now
        else:
            return None

    result = await _detector.predict()
    return result


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_recent_predictions(limit: int) -> list:
    """Fetch the most recent `limit` prediction_log rows (newest first)."""
    try:
        from database import get_db, init_db
        await init_db()
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                """SELECT predicted_direction, confidence, prediction_correct,
                          predicted_at, ticker
                   FROM prediction_log
                   WHERE excluded_from_stats = 0
                     OR excluded_from_stats IS NULL
                   ORDER BY predicted_at DESC
                   LIMIT ?""",
                (limit,),
            ) as cur:
                return await cur.fetchall()
    except Exception as exc:
        logger.error("_fetch_recent_predictions failed: %s", exc)
        return []


# ── Reason builder ────────────────────────────────────────────────────────────

def _build_reason(is_anomaly: bool, score: float, features: dict) -> str:
    """Generate a human-readable explanation of the anomaly score."""
    if not is_anomaly:
        return f"Normal signal pattern (score={score:.3f})"

    parts = []
    if features["mean_confidence"] < 0.25:
        parts.append(f"very low mean confidence ({features['mean_confidence']*100:.0f}%)")
    if features["confidence_stddev"] > 0.25:
        parts.append(f"high confidence variance (σ={features['confidence_stddev']*100:.0f}%)")
    if features["neutral_ratio"] > 0.6:
        parts.append(f"dominant neutral signals ({features['neutral_ratio']*100:.0f}%)")
    if features["accuracy_rate"] < 0.35:
        parts.append(f"low accuracy rate ({features['accuracy_rate']*100:.0f}%)")
    if features["bull_ratio"] > 0.85 or features["bear_ratio"] > 0.85:
        dominant = "bullish" if features["bull_ratio"] > features["bear_ratio"] else "bearish"
        ratio = max(features["bull_ratio"], features["bear_ratio"])
        parts.append(f"extreme {dominant} skew ({ratio*100:.0f}%)")

    if not parts:
        parts.append(f"unusual feature combination (score={score:.3f})")

    return "Anomaly detected: " + "; ".join(parts)
