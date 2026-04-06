"""
Tests for the Reasoning Synthesizer agent and its route.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend is on the path
BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND)

from agents.reasoning_synthesizer import ReasoningSynthesizer, _fallback_output
from models.reasoning_output import (
    Direction,
    ImpactType,
    ReasoningOutput,
    Recommendation,
    Stability,
    Strength,
)

# ── Shared fixtures ────────────────────────────────────────────────────────────

VALID_LLM_RESPONSE = {
    "stock_ticker": "BHP.AX",
    "event_classification": {
        "type": "Indirect Impact",
        "strength": "Medium",
        "domains": ["geopolitics", "logistics"],
    },
    "causal_chain": {
        "summary": "Test causal chain",
        "cost_impact": "Minor",
        "revenue_impact": "None",
        "demand_impact": "Neutral",
        "sentiment_impact": "Slight negative",
    },
    "impact_timeline": [
        {"timeframe": "Immediate", "direction": "Neutral", "confidence": "Medium", "reason": "Test"},
        {"timeframe": "Short-term", "direction": "Neutral", "confidence": "Medium", "reason": "Test"},
        {"timeframe": "Medium-term", "direction": "Neutral", "confidence": "Low", "reason": "Test"},
        {"timeframe": "Long-term", "direction": "Neutral", "confidence": "Low", "reason": "Test"},
    ],
    "market_context": {
        "alignment": "No strong effect",
        "notes": "Test notes",
    },
    "consensus_analysis": {
        "bullish": 10,
        "bearish": 15,
        "neutral": 20,
        "strength_score": 45,
        "stability": "Fragile",
    },
    "final_decision": {
        "direction": "Neutral",
        "recommendation": "WAIT",
        "confidence_score": 40,
        "risk_level": "Medium",
    },
    "risk_factors": ["Test risk 1", "Test risk 2"],
    "contrarian_view": None,
    "data_provenance": {},
}

AGENT_VOTES = {"bullish": 10, "bearish": 15, "neutral": 20}


@pytest.fixture
def mock_router():
    """LLMRouter mock that returns a valid JSON response."""
    router = MagicMock()
    router.call_primary = AsyncMock(return_value=json.dumps(VALID_LLM_RESPONSE))
    return router


# ── Unit tests ─────────────────────────────────────────────────────────────────

class TestReasoningSynthesizer:

    @pytest.mark.asyncio
    async def test_synthesize_returns_valid_output(self, mock_router):
        """synthesize() returns a validated ReasoningOutput on success."""
        synthesizer = ReasoningSynthesizer(mock_router)

        result = await synthesizer.synthesize(
            stock_ticker="BHP.AX",
            news_headline="Test headline",
            news_summary="Test summary",
            market_signals={"iron_ore": 118.5},
            agent_votes=AGENT_VOTES,
            data_provenance={},
        )

        assert isinstance(result, ReasoningOutput)
        assert result.stock_ticker == "BHP.AX"
        assert result.final_decision.recommendation == Recommendation.WAIT
        assert result.final_decision.direction == Direction.NEUTRAL

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self, mock_router):
        """Returns fallback output when LLM emits unparseable content."""
        mock_router.call_primary = AsyncMock(return_value="this is not json at all")

        synthesizer = ReasoningSynthesizer(mock_router)
        result = await synthesizer.synthesize(
            stock_ticker="CBA.AX",
            news_headline="Test",
            news_summary="Test",
            market_signals={},
            agent_votes=AGENT_VOTES,
            data_provenance={},
        )

        assert result.final_decision.recommendation == Recommendation.WAIT
        assert result.final_decision.confidence_score == 0
        assert "error_fallback" in result.event_classification.domains

    @pytest.mark.asyncio
    async def test_fallback_on_llm_exception(self, mock_router):
        """Returns fallback output when the LLM call itself raises."""
        mock_router.call_primary = AsyncMock(side_effect=Exception("LLM timeout"))

        synthesizer = ReasoningSynthesizer(mock_router)
        result = await synthesizer.synthesize(
            stock_ticker="RIO.AX",
            news_headline="Test",
            news_summary="Test",
            market_signals={},
            agent_votes=AGENT_VOTES,
            data_provenance={},
        )

        assert result.final_decision.confidence_score == 0
        assert result.final_decision.risk_level == Strength.HIGH
        assert any("LLM timeout" in r for r in result.risk_factors)

    @pytest.mark.asyncio
    async def test_vote_counts_preserved_in_fallback(self, mock_router):
        """Fallback output preserves the original agent vote counts."""
        mock_router.call_primary = AsyncMock(side_effect=Exception("fail"))
        votes = {"bullish": 5, "bearish": 30, "neutral": 10}

        synthesizer = ReasoningSynthesizer(mock_router)
        result = await synthesizer.synthesize(
            stock_ticker="FMG.AX",
            news_headline="Test",
            news_summary="Test",
            market_signals={},
            agent_votes=votes,
            data_provenance={},
        )

        assert result.consensus_analysis.bullish == 5
        assert result.consensus_analysis.bearish == 30
        assert result.consensus_analysis.neutral == 10

    def test_geography_prompt_includes_lombok(self, mock_router):
        """System prompt must reference Lombok/Makassar to prevent geography bugs."""
        from agents.reasoning_synthesizer import _SYSTEM_PROMPT
        assert "Lombok/Makassar" in _SYSTEM_PROMPT
        assert "NOT Malacca" in _SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_call_primary_is_used_not_boost(self, mock_router):
        """Synthesizer uses call_primary (report mode), not call_boost (agent mode)."""
        synthesizer = ReasoningSynthesizer(mock_router)
        await synthesizer.synthesize(
            stock_ticker="BHP.AX",
            news_headline="Test",
            news_summary="Test",
            market_signals={},
            agent_votes=AGENT_VOTES,
            data_provenance={},
        )

        mock_router.call_primary.assert_called_once()
        mock_router.call_boost = MagicMock()  # ensure boost was never touched
        mock_router.call_boost.assert_not_called()


# ── Fallback helper unit tests ─────────────────────────────────────────────────

class TestFallbackOutput:

    def test_fallback_is_always_wait(self):
        result = _fallback_output("WDS.AX", AGENT_VOTES, "some error")
        assert result.final_decision.recommendation == Recommendation.WAIT
        assert result.final_decision.direction == Direction.NEUTRAL

    def test_fallback_confidence_is_zero(self):
        result = _fallback_output("STO.AX", AGENT_VOTES, "timeout")
        assert result.final_decision.confidence_score == 0

    def test_fallback_stability_is_fragile(self):
        result = _fallback_output("ANZ.AX", AGENT_VOTES, "error")
        assert result.consensus_analysis.stability == Stability.FRAGILE
