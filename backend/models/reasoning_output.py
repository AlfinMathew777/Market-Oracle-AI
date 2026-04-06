"""Pydantic models for the Reasoning Synthesizer agent output."""

import json
from pydantic import BaseModel, Field, field_validator
from typing import Any, List, Literal, Optional
from enum import Enum


class ImpactType(str, Enum):
    DIRECT = "Direct Impact"
    INDIRECT = "Indirect Impact"
    NOISE = "Noise / Low Relevance"


class Strength(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Direction(str, Enum):
    BULLISH = "Bullish"
    BEARISH = "Bearish"
    NEUTRAL = "Neutral"


class Recommendation(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WAIT = "WAIT"


class Stability(str, Enum):
    STABLE = "Stable"
    FRAGILE = "Fragile"


class EventClassification(BaseModel):
    type: ImpactType
    strength: Strength
    domains: List[str] = Field(..., description="Affected domains: oil, iron_ore, currency, demand, logistics, etc.")


class CausalChain(BaseModel):
    summary: str = Field(..., description="Event → Intermediate Effects → Company Impact")
    cost_impact: str
    revenue_impact: str
    demand_impact: str
    sentiment_impact: str


class TimelineEntry(BaseModel):
    timeframe: Literal["Immediate", "Short-term", "Medium-term", "Long-term"]
    direction: Direction
    confidence: Strength
    reason: str


class MarketContext(BaseModel):
    alignment: Literal["Reinforces trend", "Contradicts trend", "No strong effect"]
    commodity_signals: dict = Field(default_factory=dict)
    currency_signal: Optional[str] = None
    technical_summary: Optional[str] = None
    notes: str

    @field_validator("currency_signal", "technical_summary", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> Optional[str]:
        """LLMs sometimes return dicts/lists for string fields — coerce gracefully."""
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return json.dumps(v)


class ConsensusAnalysis(BaseModel):
    bullish: int
    bearish: int
    neutral: int
    strength_score: int = Field(..., ge=0, le=100)
    stability: Stability


class FinalDecision(BaseModel):
    direction: Direction
    recommendation: Recommendation
    confidence_score: int = Field(..., ge=0, le=100)
    risk_level: Strength


class ReasoningOutput(BaseModel):
    """Complete structured output from the Reasoning Synthesizer."""
    stock_ticker: str
    event_classification: EventClassification
    causal_chain: CausalChain
    impact_timeline: List[TimelineEntry]
    market_context: MarketContext
    consensus_analysis: ConsensusAnalysis
    final_decision: FinalDecision
    risk_factors: List[str]
    contrarian_view: Optional[str] = None
    data_provenance: dict = Field(
        default_factory=dict,
        description="Source timestamps for all market data used",
    )
    # Populated by ReasoningSynthesizer after memory injection — not from LLM
    memory_context: Optional[dict] = Field(
        default=None,
        exclude=True,
        description="Historical memory context used for this prediction (internal, not serialised)",
    )

    model_config = {"extra": "allow"}
