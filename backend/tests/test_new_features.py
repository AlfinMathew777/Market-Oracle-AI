"""
Unit tests for newly implemented features:
- News Classification (13 categories)
- CVaR/VaR Risk Metrics
- Prediction Evaluator (F1/Precision/Recall)
- Failure Analyzer (Data Flywheel)

Run with: pytest tests/test_new_features.py -v
"""

import sys
import os

import numpy as np
import pytest

# Add backend root to path so imports work without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# NEWS CLASSIFIER TESTS
# ============================================================

class TestNewsClassifier:
    """Test news classification into 13 categories."""

    @pytest.fixture
    def classifier(self):
        from services.news_classifier import NewsClassifier
        return NewsClassifier()

    @pytest.mark.asyncio
    async def test_earnings_classification(self, classifier):
        """Test earnings news detection."""
        for headline in [
            "BHP reports record quarterly profit",
            "Company beats earnings estimates by 15%",
            "Annual results show revenue growth",
            "EPS comes in above expectations",
        ]:
            result = await classifier.classify(headline, "")
            assert result.category.value == "earnings", (
                f"Expected earnings, got {result.category.value!r} for: {headline}"
            )
            assert result.confidence >= 0.5

    @pytest.mark.asyncio
    async def test_commodity_classification(self, classifier):
        """Test commodity price news detection."""
        for headline in [
            "Iron ore prices surge 5% overnight",
            "Oil price drops to $70/barrel",
            "Gold hits record high",
            "Copper futures rally on demand",
        ]:
            result = await classifier.classify(headline, "")
            assert result.category.value == "commodity_price", (
                f"Expected commodity_price, got {result.category.value!r} for: {headline}"
            )

    @pytest.mark.asyncio
    async def test_management_classification(self, classifier):
        """Test management change news detection."""
        for headline in [
            "CEO announces retirement",
            "New CFO appointed from internal ranks",
            "Board director resigns",
        ]:
            result = await classifier.classify(headline, "")
            assert result.category.value == "management", (
                f"Expected management, got {result.category.value!r} for: {headline}"
            )

    @pytest.mark.asyncio
    async def test_geopolitical_classification(self, classifier):
        """Test geopolitical news detection."""
        for headline in [
            "China announces new tariffs on imports",
            "US-China trade tensions escalate",
            "Sanctions imposed on Russian exports",
        ]:
            result = await classifier.classify(headline, "")
            assert result.category.value == "geopolitical", (
                f"Expected geopolitical, got {result.category.value!r} for: {headline}"
            )

    @pytest.mark.asyncio
    async def test_analyst_rating_classification(self, classifier):
        """Test analyst rating news detection."""
        for headline in [
            "Goldman upgrades BHP to Buy",
            "Analyst downgrades stock to Sell",
            "Price target raised to $60",
            "Broker initiates coverage with Outperform",
        ]:
            result = await classifier.classify(headline, "")
            assert result.category.value == "analyst_rating", (
                f"Expected analyst_rating, got {result.category.value!r} for: {headline}"
            )

    def test_all_13_categories_exist(self):
        """Verify all 13 categories are defined."""
        from services.news_classifier import NewsCategory

        expected = {
            "earnings", "merger_acquisition", "analyst_rating",
            "commodity_price", "regulatory", "management",
            "guidance", "dividend", "legal", "macro",
            "geopolitical", "operational", "sentiment",
        }
        actual = {c.value for c in NewsCategory}
        missing = expected - actual
        assert not missing, f"Missing categories: {missing}"

    @pytest.mark.asyncio
    async def test_classification_returns_materiality(self, classifier):
        """Verify materiality is returned and valid."""
        result = await classifier.classify("Iron ore surges 5%", "")
        assert result.materiality in {"HIGH", "MEDIUM", "LOW"}

    @pytest.mark.asyncio
    async def test_classification_returns_focus(self, classifier):
        """Verify recommended focus is a non-empty string."""
        result = await classifier.classify("BHP reports earnings", "")
        assert isinstance(result.recommended_focus, str)
        assert len(result.recommended_focus) > 0

    @pytest.mark.asyncio
    async def test_confidence_in_unit_range(self, classifier):
        """Confidence must be between 0 and 1."""
        result = await classifier.classify("Dividend announced", "")
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_to_dict_serializable(self, classifier):
        """to_dict() must return JSON-serializable structure."""
        import json
        result = await classifier.classify("Iron ore surges 5%", "")
        d = result.to_dict()
        json.dumps(d)  # raises if not serializable
        assert "category" in d
        assert "confidence" in d
        assert "materiality" in d


# ============================================================
# CVAR OPTIMIZER TESTS
# ============================================================

class TestCVaROptimizer:
    """Test CVaR/VaR risk calculations."""

    @pytest.fixture
    def optimizer(self):
        from services.game_theory.cvar_optimizer import CVaROptimizer
        return CVaROptimizer(n_scenarios=10000, seed=42)

    @pytest.fixture
    def normal_returns(self):
        """Standard normal returns with 2% daily vol (fractional)."""
        rng = np.random.default_rng(42)
        return rng.normal(0, 0.02, 10000)

    def test_var_calculation(self, optimizer, normal_returns):
        """VaR 95% for 2% vol should be approximately -3.3% (1.645σ)."""
        var_95 = optimizer.calculate_var(normal_returns, 0.95)
        assert -5.0 < var_95 < -2.0, f"VaR 95% out of expected range: {var_95:.2f}%"

    def test_cvar_worse_than_var(self, optimizer, normal_returns):
        """CVaR must always be <= VaR (more negative = worse loss)."""
        var_95 = optimizer.calculate_var(normal_returns, 0.95)
        cvar_95 = optimizer.calculate_cvar(normal_returns, 0.95)
        assert cvar_95 <= var_95, (
            f"CVaR {cvar_95:.2f}% must be worse than VaR {var_95:.2f}%"
        )

    def test_var_99_worse_than_var_95(self, optimizer, normal_returns):
        """99% VaR is more extreme than 95% VaR."""
        var_95 = optimizer.calculate_var(normal_returns, 0.95)
        var_99 = optimizer.calculate_var(normal_returns, 0.99)
        assert var_99 <= var_95, (
            f"VaR 99% {var_99:.2f}% should be <= VaR 95% {var_95:.2f}%"
        )

    def test_simulate_and_calculate_fields(self, optimizer):
        """All RiskMetrics fields are present after simulate_and_calculate."""
        metrics = optimizer.simulate_and_calculate(
            current_price=50.0,
            daily_volatility=0.02,
            n_days=7,
        )
        required = [
            "var_95", "cvar_95", "var_99", "cvar_99",
            "expected_return", "prob_profit", "risk_adjusted_score",
            "tail_risk_ratio", "n_scenarios", "n_days",
        ]
        for field in required:
            assert hasattr(metrics, field), f"Missing field: {field}"

    def test_risk_level_low_volatility(self, optimizer):
        """Very low volatility → LOW or MEDIUM risk level."""
        metrics = optimizer.simulate_and_calculate(
            current_price=50.0,
            daily_volatility=0.003,
            n_days=7,
        )
        assert metrics._get_risk_level() in {"LOW", "MEDIUM"}, (
            f"Expected LOW/MEDIUM for 0.3% daily vol, got {metrics._get_risk_level()}"
        )

    def test_risk_level_high_volatility(self, optimizer):
        """High volatility → HIGH or VERY HIGH risk level."""
        metrics = optimizer.simulate_and_calculate(
            current_price=50.0,
            daily_volatility=0.05,
            n_days=7,
        )
        assert metrics._get_risk_level() in {"HIGH", "VERY HIGH"}, (
            f"Expected HIGH/VERY HIGH for 5% daily vol, got {metrics._get_risk_level()}"
        )

    def test_prob_profit_range(self, optimizer):
        """Probability of profit must be in [0, 100]."""
        metrics = optimizer.simulate_and_calculate(
            current_price=50.0,
            daily_volatility=0.02,
            n_days=7,
        )
        assert 0.0 <= metrics.prob_profit <= 100.0

    def test_to_dict_serializable(self, optimizer):
        """to_dict() must be JSON-serializable and contain required keys."""
        import json
        metrics = optimizer.simulate_and_calculate(
            current_price=50.0,
            daily_volatility=0.02,
            n_days=7,
        )
        d = metrics.to_dict()
        json.dumps(d)  # raises if not serializable
        for key in ("var_95", "cvar_95", "risk_level", "var_95_interpretation", "cvar_95_interpretation"):
            assert key in d, f"Missing key in to_dict(): {key}"

    def test_calculate_from_returns(self, optimizer, normal_returns):
        """calculate_from_returns produces valid metrics from pre-simulated array."""
        metrics = optimizer.calculate_from_returns(
            returns=normal_returns,
            current_price=50.0,
            n_days=7,
        )
        assert metrics.n_scenarios == len(normal_returns)
        assert metrics.current_price == 50.0
        assert metrics.cvar_95 <= metrics.var_95

    def test_calculate_cvar_metrics_convenience(self):
        """Convenience function returns dict with required keys."""
        from services.game_theory.cvar_optimizer import calculate_cvar_metrics
        result = calculate_cvar_metrics(
            current_price=50.0,
            daily_volatility=0.02,
            n_days=7,
            n_scenarios=1000,
        )
        for key in ("var_95", "cvar_95", "risk_level", "interpretations"):
            assert key in result, f"Missing key: {key}"


# ============================================================
# PREDICTION EVALUATOR TESTS
# ============================================================

class TestPredictionEvaluator:
    """Test F1/Precision/Recall calculations."""

    @pytest.fixture
    def evaluator(self):
        from services.prediction_evaluator import PredictionEvaluator
        return PredictionEvaluator()

    def test_perfect_accuracy(self, evaluator):
        """100% correct predictions → accuracy=1, F1=1."""
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
            {"predicted_direction": "NEUTRAL", "actual_direction": "NEUTRAL"},
        ]
        result = evaluator.evaluate(predictions)
        assert result.accuracy == 1.0
        assert result.f1_macro == pytest.approx(1.0, abs=1e-6)

    def test_zero_accuracy(self, evaluator):
        """All wrong predictions → accuracy=0."""
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BEARISH"},
            {"predicted_direction": "BEARISH", "actual_direction": "NEUTRAL"},
            {"predicted_direction": "NEUTRAL", "actual_direction": "BULLISH"},
        ]
        result = evaluator.evaluate(predictions)
        assert result.accuracy == 0.0

    def test_mixed_accuracy(self, evaluator):
        """3/4 correct → accuracy=0.75."""
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BULLISH", "actual_direction": "BEARISH"},
            {"predicted_direction": "NEUTRAL", "actual_direction": "NEUTRAL"},
            {"predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
        ]
        result = evaluator.evaluate(predictions)
        assert result.accuracy == pytest.approx(0.75)
        assert 0.0 < result.f1_macro < 1.0

    def test_empty_predictions(self, evaluator):
        """Empty input returns zero result without crashing."""
        result = evaluator.evaluate([])
        assert result.accuracy == 0
        assert result.f1_macro == 0
        assert result.total_predictions == 0

    def test_per_class_counts(self, evaluator):
        """Per-class counts must match ground truth distribution."""
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BULLISH", "actual_direction": "BEARISH"},
            {"predicted_direction": "NEUTRAL", "actual_direction": "BULLISH"},
        ]
        result = evaluator.evaluate(predictions)
        # 3 actual BULLISH, 2 predicted correctly
        assert result.bullish_total == 3
        assert result.bullish_correct == 2

    def test_confusion_matrix_shape(self, evaluator):
        """Confusion matrix must be 3×3."""
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
        ]
        result = evaluator.evaluate(predictions)
        assert len(result.confusion_matrix) == 3
        assert all(len(row) == 3 for row in result.confusion_matrix)

    def test_confusion_matrix_sums_to_total(self, evaluator):
        """All confusion matrix cells must sum to total predictions."""
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BEARISH", "actual_direction": "NEUTRAL"},
            {"predicted_direction": "NEUTRAL", "actual_direction": "BEARISH"},
        ]
        result = evaluator.evaluate(predictions)
        cm_total = sum(cell for row in result.confusion_matrix for cell in row)
        assert cm_total == len(predictions)

    def test_to_dict_structure(self, evaluator):
        """to_dict() contains required top-level keys."""
        import json
        predictions = [{"predicted_direction": "BULLISH", "actual_direction": "BULLISH"}]
        d = evaluator.evaluate(predictions).to_dict()
        json.dumps(d)
        for key in ("overall", "per_class", "confusion_matrix", "sample_counts"):
            assert key in d, f"Missing key: {key}"
        for direction in ("BULLISH", "BEARISH", "NEUTRAL"):
            assert direction in d["per_class"]

    def test_unknown_direction_treated_as_neutral(self, evaluator):
        """Unrecognised direction values fall back to NEUTRAL without crash."""
        predictions = [
            {"predicted_direction": "SIDEWAYS", "actual_direction": "UP"},
        ]
        result = evaluator.evaluate(predictions)  # must not raise
        assert result.total_predictions == 1

    def test_evaluate_predictions_convenience(self):
        """Convenience function returns dict directly."""
        from services.prediction_evaluator import evaluate_predictions
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
        ]
        d = evaluate_predictions(predictions)
        assert "overall" in d


# ============================================================
# FAILURE ANALYZER TESTS
# ============================================================

class TestFailureAnalyzer:
    """Test failure pattern analysis and data flywheel report."""

    @pytest.fixture
    def analyzer(self):
        from services.failure_analyzer import FailureAnalyzer
        return FailureAnalyzer()

    def test_no_failures(self, analyzer):
        """No failures → zero failure rate and positive-message recommendations."""
        predictions = [
            {"was_correct": True, "predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"was_correct": True, "predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
        ]
        report = analyzer.generate_flywheel_report(predictions)
        assert report.total_failures == 0
        assert report.failure_rate == 0.0
        assert len(report.prompt_recommendations) > 0

    def test_all_failures(self, analyzer):
        """All incorrect → failure_rate=1.0."""
        predictions = [
            {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 50},
            {"was_correct": False, "predicted_direction": "BEARISH", "actual_direction": "BULLISH", "confidence": 50},
        ]
        report = analyzer.generate_flywheel_report(predictions)
        assert report.total_failures == 2
        assert report.failure_rate == pytest.approx(1.0)

    def test_mixed_failure_rate(self, analyzer):
        """50% failure rate calculated correctly."""
        predictions = [
            {"was_correct": True,  "predicted_direction": "BULLISH", "actual_direction": "BULLISH", "confidence": 60},
            {"was_correct": False, "predicted_direction": "BEARISH", "actual_direction": "BULLISH", "confidence": 60},
        ]
        report = analyzer.generate_flywheel_report(predictions)
        assert report.failure_rate == pytest.approx(0.5)

    def test_overconfidence_pattern(self, analyzer):
        """High confidence + wrong direction → OVERCONFIDENCE."""
        from services.failure_analyzer import FailurePattern
        prediction = {
            "was_correct": False,
            "predicted_direction": "BULLISH",
            "actual_direction": "NEUTRAL",
            "confidence": 85,
        }
        analysis = analyzer.analyze_failure(prediction)
        assert analysis.pattern == FailurePattern.OVERCONFIDENCE

    def test_wrong_direction_strong_consensus(self, analyzer):
        """High-confidence directional flip with strong consensus → WRONG_DIRECTION."""
        from services.failure_analyzer import FailurePattern
        prediction = {
            "was_correct": False,
            "predicted_direction": "BULLISH",
            "actual_direction": "BEARISH",
            "confidence": 75,
            "agent_votes": {"bullish": 30, "bearish": 5, "neutral": 10},
        }
        analysis = analyzer.analyze_failure(prediction)
        assert analysis.pattern in {FailurePattern.WRONG_DIRECTION, FailurePattern.OVERCONFIDENCE}

    def test_underconfidence_pattern(self, analyzer):
        """Low confidence + missed directional move → UNDERCONFIDENCE."""
        from services.failure_analyzer import FailurePattern
        prediction = {
            "was_correct": False,
            "predicted_direction": "NEUTRAL",
            "actual_direction": "BULLISH",
            "confidence": 28,
        }
        analysis = analyzer.analyze_failure(prediction)
        assert analysis.pattern in {FailurePattern.UNDERCONFIDENCE, FailurePattern.MISSED_CATALYST}

    def test_recommendations_generated(self, analyzer):
        """At least one recommendation is always produced for a failed set."""
        predictions = [
            {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 80},
            {"was_correct": False, "predicted_direction": "NEUTRAL", "actual_direction": "BULLISH", "confidence": 35},
        ]
        report = analyzer.generate_flywheel_report(predictions)
        assert len(report.prompt_recommendations) > 0

    def test_top_patterns_sorted_by_frequency(self, analyzer):
        """Top patterns list is sorted highest-count first."""
        predictions = [
            {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 80},
            {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 75},
            {"was_correct": False, "predicted_direction": "NEUTRAL", "actual_direction": "BULLISH", "confidence": 35},
        ]
        report = analyzer.generate_flywheel_report(predictions)
        if len(report.top_patterns) >= 2:
            first = report.pattern_counts.get(report.top_patterns[0], 0)
            second = report.pattern_counts.get(report.top_patterns[1], 0)
            assert first >= second

    def test_all_10_failure_patterns_exist(self):
        """All 10 FailurePattern values must be present."""
        from services.failure_analyzer import FailurePattern
        expected = {
            "missed_catalyst", "wrong_direction", "timing_off", "external_shock",
            "overconfidence", "underconfidence", "sector_mismatch", "signal_ignored",
            "consensus_wrong", "technical_failure",
        }
        actual = {p.value for p in FailurePattern}
        assert expected == actual

    def test_to_dict_structure(self, analyzer):
        """to_dict() contains required keys and is JSON-serializable."""
        import json
        predictions = [
            {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 55},
        ]
        d = analyzer.generate_flywheel_report(predictions).to_dict()
        json.dumps(d)
        for key in ("summary", "patterns", "top_issues", "recommendations", "metadata"):
            assert key in d, f"Missing key: {key}"

    def test_analyze_failures_convenience(self):
        """Convenience function returns dict directly."""
        from services.failure_analyzer import analyze_failures
        predictions = [
            {"was_correct": False, "predicted_direction": "BEARISH", "actual_direction": "BULLISH", "confidence": 50},
        ]
        d = analyze_failures(predictions)
        assert "summary" in d
        assert d["summary"]["total_failures"] == 1


# ============================================================
# INTEGRATION SMOKE TESTS
# ============================================================

class TestIntegration:
    """Lightweight integration checks — no server required."""

    @pytest.mark.asyncio
    async def test_classify_news_convenience(self):
        """classify_news() convenience function returns expected category."""
        from services.news_classifier import classify_news
        result = await classify_news("Iron ore surges 5%", "")
        assert result["category"] == "commodity_price"
        assert "materiality" in result

    def test_cvar_calculate_cvar_metrics_convenience(self):
        """calculate_cvar_metrics() returns all required keys."""
        from services.game_theory.cvar_optimizer import calculate_cvar_metrics
        result = calculate_cvar_metrics(
            current_price=50.0,
            daily_volatility=0.02,
            n_days=7,
            n_scenarios=1000,
        )
        for key in ("var_95", "cvar_95", "risk_level", "interpretations"):
            assert key in result

    def test_evaluate_predictions_convenience(self):
        """evaluate_predictions() convenience function works end-to-end."""
        from services.prediction_evaluator import evaluate_predictions
        predictions = [
            {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"predicted_direction": "BEARISH", "actual_direction": "NEUTRAL"},
        ]
        d = evaluate_predictions(predictions)
        assert d["overall"]["accuracy"] == pytest.approx(50.0)

    def test_analyze_failures_convenience(self):
        """analyze_failures() convenience function works end-to-end."""
        from services.failure_analyzer import analyze_failures
        predictions = [
            {"was_correct": True,  "predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
            {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 80},
        ]
        d = analyze_failures(predictions)
        assert d["summary"]["failure_rate"] == pytest.approx(50.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
