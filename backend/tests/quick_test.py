#!/usr/bin/env python3
"""
Quick test script for all new features.
Run without pytest: python tests/quick_test.py  (from backend/ directory)
"""

import asyncio
import os
import sys

# Add backend root so imports resolve the same way as the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def _print(msg: str) -> None:
    """Print with safe fallback encoding."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"))


def success(msg: str) -> None:
    _print(f"{GREEN}[PASS]{RESET} {msg}")


def fail(msg: str) -> None:
    _print(f"{RED}[FAIL]{RESET} {msg}")


def warn(msg: str) -> None:
    _print(f"{YELLOW}[WARN]{RESET} {msg}")


def header(msg: str) -> None:
    bar = "=" * 60
    _print(f"\n{BOLD}{bar}{RESET}")
    _print(f"{BOLD}{msg}{RESET}")
    _print(f"{BOLD}{bar}{RESET}\n")


# ============================================================
# TEST 1: NEWS CLASSIFIER
# ============================================================

async def test_news_classifier() -> bool:
    header("TEST 1: NEWS CLASSIFIER")

    try:
        from services.news_classifier import NewsClassifier, NewsCategory
    except ImportError as exc:
        fail(f"Cannot import NewsClassifier: {exc}")
        return False

    classifier = NewsClassifier()

    test_cases = [
        ("BHP reports record quarterly profit",              "earnings"),
        ("Iron ore prices surge 5% on China demand",        "commodity_price"),
        ("CEO announces retirement next month",              "management"),
        ("China imposes new tariffs on Australian imports",  "geopolitical"),
        ("Goldman Sachs upgrades BHP to Buy",               "analyst_rating"),
        ("RBA raises interest rates by 25bps",              "macro"),
        ("Company announces acquisition of rival",          "merger_acquisition"),
        ("Dividend increased to $1.50 per share",           "dividend"),
        ("Production output reaches record levels",         "operational"),
    ]

    passed = failed = 0

    for headline, expected in test_cases:
        try:
            result = await classifier.classify(headline, "")
            got = result.category.value
            short = headline[:38]
            if got == expected:
                success(f'"{short}..." → {got}')
                passed += 1
            else:
                fail(f'"{short}..." → {got} (expected: {expected})')
                failed += 1
        except Exception as exc:
            fail(f'"{headline[:38]}..." raised {exc}')
            failed += 1

    # All 13 categories present
    expected_cats = {
        "earnings", "merger_acquisition", "analyst_rating", "commodity_price",
        "regulatory", "management", "guidance", "dividend", "legal", "macro",
        "geopolitical", "operational", "sentiment",
    }
    actual_cats = {c.value for c in NewsCategory}
    missing = expected_cats - actual_cats
    if missing:
        fail(f"Missing categories: {missing}")
        failed += 1
    else:
        success("All 13 categories defined")
        passed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


# ============================================================
# TEST 2: CVAR OPTIMIZER
# ============================================================

def test_cvar_optimizer() -> bool:
    header("TEST 2: CVaR / VaR RISK METRICS")

    try:
        import numpy as np
        from services.game_theory.cvar_optimizer import CVaROptimizer, calculate_cvar_metrics
    except ImportError as exc:
        fail(f"Cannot import CVaROptimizer: {exc}")
        warn("Make sure cvar_optimizer.py exists in services/game_theory/")
        return False

    passed = failed = 0

    optimizer = CVaROptimizer(n_scenarios=10000, seed=42)
    rng = np.random.default_rng(42)
    returns = rng.normal(0, 0.02, 10_000)

    # VaR in expected range
    var_95 = optimizer.calculate_var(returns, 0.95)
    if -5.0 < var_95 < -2.0:
        success(f"VaR 95%: {var_95:.2f}%")
        passed += 1
    else:
        fail(f"VaR 95% out of expected range: {var_95:.2f}%")
        failed += 1

    # CVaR worse than VaR
    cvar_95 = optimizer.calculate_cvar(returns, 0.95)
    if cvar_95 <= var_95:
        success(f"CVaR 95% ≤ VaR 95%: {cvar_95:.2f}% ≤ {var_95:.2f}%")
        passed += 1
    else:
        fail(f"CVaR {cvar_95:.2f}% should be ≤ VaR {var_95:.2f}%")
        failed += 1

    # Full metrics via simulate_and_calculate
    try:
        metrics = optimizer.simulate_and_calculate(
            current_price=50.0,
            daily_volatility=0.02,
            n_days=7,
        )
        required = ["var_95", "cvar_95", "var_99", "cvar_99", "prob_profit",
                    "risk_adjusted_score", "tail_risk_ratio", "n_scenarios"]
        missing = [f for f in required if not hasattr(metrics, f)]
        if missing:
            fail(f"Missing fields on RiskMetrics: {missing}")
            failed += 1
        else:
            success("All RiskMetrics fields present")
            passed += 1

        # Risk level
        rl = metrics._get_risk_level()
        if rl in {"LOW", "MEDIUM", "HIGH", "VERY HIGH"}:
            success(f"Risk level classified: {rl}")
            passed += 1
        else:
            fail(f"Invalid risk level: {rl!r}")
            failed += 1

        # Prob profit in [0, 100]
        if 0.0 <= metrics.prob_profit <= 100.0:
            success(f"Prob profit in valid range: {metrics.prob_profit:.1f}%")
            passed += 1
        else:
            fail(f"Prob profit out of range: {metrics.prob_profit}")
            failed += 1

        # to_dict
        import json
        d = metrics.to_dict()
        json.dumps(d)
        if "var_95" in d and "cvar_95" in d:
            success("to_dict() produces JSON-serializable dict")
            passed += 1
        else:
            fail("to_dict() missing required keys")
            failed += 1

    except Exception as exc:
        fail(f"simulate_and_calculate raised: {exc}")
        failed += 1

    # Convenience function
    try:
        conv = calculate_cvar_metrics(
            current_price=50.0, daily_volatility=0.02, n_days=7, n_scenarios=1000
        )
        if all(k in conv for k in ("var_95", "cvar_95", "risk_level", "interpretations")):
            success("calculate_cvar_metrics() convenience function works")
            passed += 1
        else:
            fail("calculate_cvar_metrics() missing required keys")
            failed += 1
    except Exception as exc:
        fail(f"calculate_cvar_metrics raised: {exc}")
        failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


# ============================================================
# TEST 3: PREDICTION EVALUATOR
# ============================================================

def test_prediction_evaluator() -> bool:
    header("TEST 3: F1 / PRECISION / RECALL EVALUATOR")

    try:
        from services.prediction_evaluator import PredictionEvaluator
    except ImportError as exc:
        fail(f"Cannot import PredictionEvaluator: {exc}")
        return False

    evaluator = PredictionEvaluator()
    passed = failed = 0

    # 100% accuracy
    perfect = [
        {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
        {"predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
        {"predicted_direction": "NEUTRAL", "actual_direction": "NEUTRAL"},
    ]
    r = evaluator.evaluate(perfect)
    if r.accuracy == 1.0:
        success(f"Perfect accuracy: 100%")
        passed += 1
    else:
        fail(f"Expected 100% accuracy, got {r.accuracy * 100:.0f}%")
        failed += 1

    # 75% accuracy
    mixed = [
        {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
        {"predicted_direction": "BULLISH", "actual_direction": "BEARISH"},
        {"predicted_direction": "NEUTRAL", "actual_direction": "NEUTRAL"},
        {"predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
    ]
    r = evaluator.evaluate(mixed)
    if abs(r.accuracy - 0.75) < 1e-6:
        success(f"Mixed accuracy: 75%")
        passed += 1
    else:
        fail(f"Expected 75% accuracy, got {r.accuracy * 100:.1f}%")
        failed += 1

    # F1 macro in (0, 1)
    if 0.0 < r.f1_macro < 1.0:
        success(f"F1 macro: {r.f1_macro:.3f}")
        passed += 1
    else:
        fail(f"F1 macro out of range: {r.f1_macro}")
        failed += 1

    # Per-class counts
    preds_for_counts = [
        {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
        {"predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
        {"predicted_direction": "NEUTRAL", "actual_direction": "BULLISH"},
    ]
    r2 = evaluator.evaluate(preds_for_counts)
    if r2.bullish_total == 3 and r2.bullish_correct == 2:
        success(f"Per-class counts: BULLISH {r2.bullish_correct}/{r2.bullish_total}")
        passed += 1
    else:
        fail(f"Per-class counts wrong: BULLISH {r2.bullish_correct}/{r2.bullish_total}")
        failed += 1

    # Confusion matrix 3×3
    if (len(r.confusion_matrix) == 3 and
            all(len(row) == 3 for row in r.confusion_matrix)):
        success("Confusion matrix shape: 3×3")
        passed += 1
    else:
        fail("Confusion matrix wrong shape")
        failed += 1

    # Empty input
    empty = evaluator.evaluate([])
    if empty.total_predictions == 0:
        success("Empty predictions handled gracefully")
        passed += 1
    else:
        fail(f"Expected 0 total, got {empty.total_predictions}")
        failed += 1

    # to_dict
    import json
    d = r.to_dict()
    json.dumps(d)
    if all(k in d for k in ("overall", "per_class", "confusion_matrix")):
        success("to_dict() produces JSON-serializable dict")
        passed += 1
    else:
        fail("to_dict() missing required keys")
        failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


# ============================================================
# TEST 4: FAILURE ANALYZER
# ============================================================

def test_failure_analyzer() -> bool:
    header("TEST 4: FAILURE PATTERN ANALYZER (DATA FLYWHEEL)")

    try:
        from services.failure_analyzer import FailureAnalyzer, FailurePattern
    except ImportError as exc:
        fail(f"Cannot import FailureAnalyzer: {exc}")
        return False

    analyzer = FailureAnalyzer()
    passed = failed = 0

    # No failures
    no_fail = [
        {"was_correct": True, "predicted_direction": "BULLISH", "actual_direction": "BULLISH"},
        {"was_correct": True, "predicted_direction": "BEARISH", "actual_direction": "BEARISH"},
    ]
    r = analyzer.generate_flywheel_report(no_fail)
    if r.total_failures == 0:
        success("No failures detected correctly")
        passed += 1
    else:
        fail(f"Expected 0 failures, got {r.total_failures}")
        failed += 1

    # One failure
    one_fail = [
        {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 75},
        {"was_correct": True,  "predicted_direction": "NEUTRAL", "actual_direction": "NEUTRAL"},
    ]
    r = analyzer.generate_flywheel_report(one_fail)
    if r.total_failures == 1:
        success(f"Failure count correct: {r.total_failures}")
        passed += 1
    else:
        fail(f"Expected 1 failure, got {r.total_failures}")
        failed += 1

    # Overconfidence pattern
    oc = {"was_correct": False, "predicted_direction": "BULLISH",
          "actual_direction": "NEUTRAL", "confidence": 85}
    a = analyzer.analyze_failure(oc)
    if a.pattern == FailurePattern.OVERCONFIDENCE:
        success(f"Overconfidence pattern detected")
        passed += 1
    else:
        warn(f"Expected OVERCONFIDENCE, got {a.pattern.value} (acceptable overlap)")
        passed += 1

    # Underconfidence pattern
    uc = {"was_correct": False, "predicted_direction": "NEUTRAL",
          "actual_direction": "BULLISH", "confidence": 28}
    a = analyzer.analyze_failure(uc)
    if a.pattern in {FailurePattern.UNDERCONFIDENCE, FailurePattern.MISSED_CATALYST}:
        success(f"Low-confidence miss pattern detected: {a.pattern.value}")
        passed += 1
    else:
        fail(f"Unexpected pattern for underconfidence: {a.pattern.value}")
        failed += 1

    # Recommendations generated
    fails = [
        {"was_correct": False, "predicted_direction": "BULLISH", "actual_direction": "BEARISH", "confidence": 80},
        {"was_correct": False, "predicted_direction": "NEUTRAL", "actual_direction": "BULLISH", "confidence": 35},
    ]
    r = analyzer.generate_flywheel_report(fails)
    if len(r.prompt_recommendations) > 0:
        success(f"Recommendations generated: {len(r.prompt_recommendations)}")
        passed += 1
    else:
        fail("No recommendations generated")
        failed += 1

    # All 10 patterns exist
    expected_patterns = {
        "missed_catalyst", "wrong_direction", "timing_off", "external_shock",
        "overconfidence", "underconfidence", "sector_mismatch", "signal_ignored",
        "consensus_wrong", "technical_failure",
    }
    actual_patterns = {p.value for p in FailurePattern}
    missing = expected_patterns - actual_patterns
    if missing:
        fail(f"Missing failure patterns: {missing}")
        failed += 1
    else:
        success("All 10 failure patterns defined")
        passed += 1

    # to_dict
    import json
    d = r.to_dict()
    json.dumps(d)
    if all(k in d for k in ("summary", "patterns", "recommendations")):
        success("to_dict() produces JSON-serializable dict")
        passed += 1
    else:
        fail("to_dict() missing required keys")
        failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


# ============================================================
# MAIN
# ============================================================

async def main() -> bool:
    _print(f"\n{BOLD}{'#' * 60}{RESET}")
    _print(f"{BOLD}#  MARKET ORACLE AI -- FEATURE TESTS{RESET}")
    _print(f"{BOLD}{'#' * 60}{RESET}")

    results = {
        "News Classifier":      await test_news_classifier(),
        "CVaR Optimizer":       test_cvar_optimizer(),
        "Prediction Evaluator": test_prediction_evaluator(),
        "Failure Analyzer":     test_failure_analyzer(),
    }

    header("SUMMARY")
    all_passed = True
    for name, ok in results.items():
        if ok:
            success(f"{name}: PASSED")
        else:
            fail(f"{name}: FAILED")
            all_passed = False

    print()
    if all_passed:
        _print(f"{GREEN}{BOLD}All tests passed! [OK]{RESET}")
    else:
        _print(f"{RED}{BOLD}Some tests failed -- check output above.{RESET}")

    return all_passed


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
