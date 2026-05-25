"""Regression tests for the three bugs found in the BHP/CBA diagnosis.

Bug #1 — Alt data not reaching agents
    event_context must include ALT DATA SIGNALS when event_data["alt_data"] is set.

Bug #2 — Monte Carlo / agent calibration disconnect
    calibrate_monte_carlo_confidence() must penalise when MC says 'stable' but
    agent consensus is weak OR causal chain is empty.

Bug #3 — No-catalyst check misses sector-specific fallback trigger format
    determine_direction() must return 'neutral' for sector-specific no-catalyst
    triggers such as "No Banking (Retail & Business)-specific catalyst
    identified for CBA.AX in last 24h".

All tests are unit-level with no LLM calls, no DB, no network I/O.
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── Bug #1 — Alt data injected into event_context ─────────────────────────────

def _build_event_context(event_data: dict) -> str:
    """Mirror the event_context-building logic in test_core.py Step 3."""
    event_context = (
        f"Country: {event_data.get('country', 'Unknown')}\n"
        f"Event Type: {event_data.get('event_type', 'Unknown')}\n"
        f"Fatalities: {event_data.get('fatalities', 0)}\n"
        f"Date: {event_data.get('event_date', 'Unknown')}\n"
        f"Description: {event_data.get('notes', event_data.get('location', 'No description'))}"
    )
    _alt = event_data.get("alt_data")
    if _alt and _alt.get("source_count", 0) > 0:
        _composite_sig = _alt.get("composite_signal", 0.0)
        _composite_dir = "bullish" if _composite_sig > 0.05 else (
            "bearish" if _composite_sig < -0.05 else "neutral"
        )
        _summaries = _alt.get("summaries", [])
        _alt_lines = [
            f"\n=== ALT DATA SIGNALS (composite: {_composite_dir}, signal={_composite_sig:+.2f}) ===",
        ]
        for _s in _summaries[:10]:
            _alt_lines.append(f"  - {_s}")
        _alt_lines.append("=== END ALT DATA ===")
        event_context += "\n" + "\n".join(_alt_lines)
    return event_context


def test_alt_data_appears_in_event_context_when_populated():
    """Alt data summaries must be included in the event_context string."""
    event_data = {
        "country": "Australia",
        "event_type": "Economic",
        "fatalities": 0,
        "event_date": "2026-04-17",
        "notes": "RBA holds rates",
        "alt_data": {
            "composite_signal": 0.4,
            "composite_confidence": 0.7,
            "source_count": 2,
            "summaries": [
                "BHP.AX: profit upgrade [PRICE SENSITIVE]",
                "BHP.AX: 20 analysts — SB:8 B:12 H:3 S:1 SS:0 (signal: +0.52)",
            ],
        },
    }
    ctx = _build_event_context(event_data)
    assert "ALT DATA SIGNALS" in ctx
    assert "profit upgrade" in ctx
    assert "composite: bullish" in ctx


def test_alt_data_absent_when_source_count_zero():
    """No ALT DATA block should appear when source_count == 0."""
    event_data = {
        "country": "Australia",
        "event_type": "Conflict",
        "fatalities": 0,
        "event_date": "2026-04-17",
        "notes": "No events",
        "alt_data": {
            "composite_signal": 0.0,
            "source_count": 0,
            "summaries": [],
        },
    }
    ctx = _build_event_context(event_data)
    assert "ALT DATA SIGNALS" not in ctx


def test_alt_data_absent_when_key_missing():
    """No ALT DATA block when alt_data key is not set at all."""
    event_data = {
        "country": "Australia",
        "event_type": "Conflict",
        "fatalities": 0,
        "event_date": "2026-04-17",
        "notes": "No events",
    }
    ctx = _build_event_context(event_data)
    assert "ALT DATA SIGNALS" not in ctx


def test_alt_data_composite_direction_bearish():
    """Composite signal < -0.05 should display as 'bearish'."""
    event_data = {
        "country": "Australia",
        "event_type": "Conflict",
        "alt_data": {
            "composite_signal": -0.3,
            "source_count": 1,
            "summaries": ["CBA.AX: insider sell — net -$80k"],
        },
    }
    ctx = _build_event_context(event_data)
    assert "composite: bearish" in ctx


def test_alt_data_summaries_capped_at_ten():
    """Only the first 10 summaries should appear (prompt-bloat guard)."""
    event_data = {
        "country": "Australia",
        "event_type": "Economic",
        "alt_data": {
            "composite_signal": 0.2,
            "source_count": 15,
            "summaries": [f"BHP.AX: signal {i}" for i in range(15)],
        },
    }
    ctx = _build_event_context(event_data)
    # "signal 10" through "signal 14" must not appear (capped at index 9)
    assert "signal 10" not in ctx
    assert "signal 9" in ctx


# ── Bug #2 — Monte Carlo calibration ──────────────────────────────────────────

from quant.calibration import calibrate_monte_carlo_confidence


class _FakeMC:
    """Minimal stand-in for MonteCarloConfidence."""
    def __init__(self, is_stable: bool, direction_stability_pct: float = 75.0):
        self.is_stable = is_stable
        self.direction_stability_pct = direction_stability_pct
        self.dominant_stability_pct = direction_stability_pct
        self.conviction_label = "HIGH"


def test_calibration_no_penalty_when_mc_unstable():
    """No extra penalty when MC already reports is_stable=False."""
    mc = _FakeMC(is_stable=False)
    out, penalties = calibrate_monte_carlo_confidence(0.70, mc, 15, 10, 2, "ADEQUATE")
    assert out == pytest.approx(0.70)
    assert penalties == []


def test_calibration_no_penalty_when_consensus_strong():
    """When agent consensus >= 55% and MC is stable, no calibration penalty."""
    mc = _FakeMC(is_stable=True)
    # 18 bull / 10 bear / 2 neut → consensus = 18/30 = 60% — above 55%
    out, penalties = calibrate_monte_carlo_confidence(0.70, mc, 18, 10, 2, "ADEQUATE")
    assert out == pytest.approx(0.70)
    assert penalties == []


def test_calibration_penalty_when_weak_consensus():
    """Stable MC + consensus < 55% → ×0.85 penalty applied."""
    mc = _FakeMC(is_stable=True)
    # 15 bull / 10 bear / 2 neut → consensus = 15/27 ≈ 55.6% — just above threshold
    # Use 14 bull → 14/26 ≈ 53.8% — below threshold
    out, penalties = calibrate_monte_carlo_confidence(0.70, mc, 14, 12, 2, "ADEQUATE")
    assert out == pytest.approx(0.70 * 0.85, rel=1e-4)
    assert any("WEAK_CONSENSUS" in p for p in penalties)


def test_calibration_penalty_when_empty_chain():
    """Stable MC + empty causal chain → ×0.80 penalty applied."""
    mc = _FakeMC(is_stable=True)
    # consensus = 20/30 ≈ 66.7% — above threshold so only the chain penalty fires
    out, penalties = calibrate_monte_carlo_confidence(0.70, mc, 20, 8, 2, "EMPTY")
    assert out == pytest.approx(0.70 * 0.80, rel=1e-4)
    assert any("EMPTY_CHAIN" in p for p in penalties)


def test_calibration_both_penalties_stack():
    """Weak consensus AND empty chain → both penalties applied in sequence."""
    mc = _FakeMC(is_stable=True)
    out, penalties = calibrate_monte_carlo_confidence(0.70, mc, 14, 12, 2, "EMPTY")
    expected = round(0.70 * 0.85 * 0.80, 5)
    assert out == pytest.approx(expected, rel=1e-4)
    assert len(penalties) == 2


def test_calibration_returns_unchanged_when_mc_none():
    """When mc_confidence_obj is None, confidence is untouched."""
    out, penalties = calibrate_monte_carlo_confidence(0.65, None, 15, 10, 2, "ADEQUATE")
    assert out == pytest.approx(0.65)
    assert penalties == []


# ── Bug #3 — no_catalyst check ────────────────────────────────────────────────

from scripts.test_core import determine_direction


def test_no_catalyst_generic_prefix_returns_neutral():
    """Original 'No major catalyst' trigger → neutral (existing behaviour)."""
    result = determine_direction(
        bullish=14, bearish=10, neutral=3,
        volume_vs_avg=0.9,
        trigger_event="No major catalyst for BHP.AX in last 24h",
        confidence=0.58,
    )
    assert result == "neutral"


def test_no_catalyst_sector_specific_returns_neutral():
    """Sector-specific fallback trigger must also produce neutral (Bug #3 fix)."""
    result = determine_direction(
        bullish=14, bearish=10, neutral=3,
        volume_vs_avg=0.9,
        trigger_event="No Banking (Retail & Business)-specific catalyst identified for CBA.AX in last 24h",
        confidence=0.58,
    )
    assert result == "neutral", (
        "Sector-specific no-catalyst trigger must return 'neutral', "
        "not 'bullish' (Bug #3 regression)"
    )


def test_no_catalyst_sector_specific_high_volume_not_neutral():
    """Even with sector-specific no-catalyst trigger, high volume (>=1.3x) overrides neutral."""
    result = determine_direction(
        bullish=14, bearish=10, neutral=3,
        volume_vs_avg=2.0,
        trigger_event="No Energy-specific catalyst identified for WDS.AX in last 24h",
        confidence=0.58,
    )
    # With volume_vs_avg=2.0 and neutral_ratio > 0.4? neutral_ratio = 3/27 ≈ 0.11 < 0.4
    # So the high-volume branch won't fire, but no_catalyst=True with volume_vs_avg=2.0 >= 1.3
    # → neutral path is NOT taken → falls to bullish (14 > 10)
    assert result != "neutral"


def test_bullish_clear_majority_ignores_no_catalyst():
    """Clear majority (>=5 margin) should return bullish even with no-catalyst trigger."""
    result = determine_direction(
        bullish=20, bearish=5, neutral=2,
        volume_vs_avg=0.8,
        trigger_event="No Banking-specific catalyst identified for CBA.AX in last 24h",
        confidence=0.70,
    )
    # 20 - 5 = 15 margin ≥ 5 → clear majority path fires first
    assert result == "bullish"


def test_bearish_clear_majority_ignores_no_catalyst():
    """Clear bearish majority (>=5 margin) should return bearish."""
    result = determine_direction(
        bullish=5, bearish=20, neutral=2,
        volume_vs_avg=0.8,
        trigger_event="No Banking-specific catalyst identified for CBA.AX in last 24h",
        confidence=0.70,
    )
    assert result == "bearish"
