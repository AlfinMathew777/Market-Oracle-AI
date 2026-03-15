"""Prediction output schema for Market Oracle AI.

Defines the structured output contract for the prediction card.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


class DirectionEnum(str, Enum):
    """Price direction prediction."""
    UP = "UP"
    DOWN = "DOWN"
    NEUTRAL = "NEUTRAL"


class TimeHorizonEnum(str, Enum):
    """Prediction time horizon."""
    H24 = "h24"  # 24 hours
    D7 = "d7"    # 7 days
    D30 = "d30"  # 30 days


class SignalType(str, Enum):
    """Types of signals contributing to prediction."""
    CONFLICT = "conflict"
    COMMODITY = "commodity"
    MACRO = "macro"
    SHIPPING = "shipping"
    MARKET_SENTIMENT = "market_sentiment"


class KeySignal(BaseModel):
    """Individual signal contributing to prediction."""
    signal_type: SignalType
    description: str
    impact: str  # "positive", "negative", "neutral"
    confidence: float = Field(ge=0, le=1)


class AgentConsensus(BaseModel):
    """Agent voting consensus breakdown."""
    up: int = Field(ge=0, description="Number of agents voting UP")
    down: int = Field(ge=0, description="Number of agents voting DOWN")
    neutral: int = Field(ge=0, description="Number of agents voting NEUTRAL")
    
    @property
    def total(self) -> int:
        return self.up + self.down + self.neutral
    
    @property
    def up_percentage(self) -> float:
        return (self.up / self.total * 100) if self.total > 0 else 0
    
    @property
    def down_percentage(self) -> float:
        return (self.down / self.total * 100) if self.total > 0 else 0


class CausalChainStep(BaseModel):
    """Single step in the causal reasoning chain."""
    step: int
    event: str
    consequence: str


class PredictionCard(BaseModel):
    """Complete prediction output for ASX ticker.
    
    This is the single source of truth for the prediction JSON schema.
    """
    # Core prediction
    ticker: str = Field(description="ASX ticker symbol (e.g., BHP.AX)")
    direction: DirectionEnum
    confidence: float = Field(ge=0, le=1, description="Confidence score 0-1")
    time_horizon: TimeHorizonEnum = Field(default=TimeHorizonEnum.D7)
    
    # Explanation
    causal_chain: List[CausalChainStep] = Field(
        description="Step-by-step causal reasoning",
        min_items=2,
        max_items=5
    )
    key_signals: List[KeySignal] = Field(
        description="Key data signals contributing to prediction",
        min_items=1
    )
    
    # Consensus
    agent_consensus: AgentConsensus = Field(
        description="50-agent voting breakdown"
    )
    
    # Metadata
    simulation_id: str
    trigger_event_id: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Optional additional context
    contrarian_view: Optional[str] = Field(
        None,
        description="Brief contrarian argument (if exists)"
    )
    risk_factors: Optional[List[str]] = Field(
        None,
        description="Key risk factors that could invalidate prediction"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "ticker": "BHP.AX",
                "direction": "UP",
                "confidence": 0.73,
                "time_horizon": "d7",
                "causal_chain": [
                    {
                        "step": 1,
                        "event": "Armed conflict escalates in Middle East (Strait of Hormuz)",
                        "consequence": "Oil supply disruption risk increases"
                    },
                    {
                        "step": 2,
                        "event": "Oil supply disruption risk increases",
                        "consequence": "Global commodity prices rise"
                    },
                    {
                        "step": 3,
                        "event": "Global commodity prices rise",
                        "consequence": "BHP's iron ore and copper exports become more valuable"
                    }
                ],
                "key_signals": [
                    {
                        "signal_type": "conflict",
                        "description": "ACLED: 15 conflict events in Middle East, 23 fatalities",
                        "impact": "negative",
                        "confidence": 0.85
                    },
                    {
                        "signal_type": "commodity",
                        "description": "Iron ore spot price +2.3% in past 24h",
                        "impact": "positive",
                        "confidence": 0.68
                    }
                ],
                "agent_consensus": {
                    "up": 37,
                    "down": 8,
                    "neutral": 5
                },
                "simulation_id": "sim_20260315_001",
                "trigger_event_id": "acled_event_12345",
                "generated_at": "2026-03-15T10:30:00Z",
                "contrarian_view": "If conflict de-escalates quickly, commodity risk premium could reverse sharply",
                "risk_factors": [
                    "Rapid diplomatic resolution",
                    "China economic slowdown reducing commodity demand",
                    "AUD strength against USD"
                ]
            }
        }


class SimulationRequest(BaseModel):
    """Request to trigger a simulation."""
    event_id: Optional[str] = None
    event_data: Optional[dict] = None
    ticker_override: Optional[str] = Field(
        None,
        description="Force simulation for specific ticker instead of auto-mapping"
    )


class SimulationResponse(BaseModel):
    """Response from simulation endpoint."""
    status: str  # "running", "completed", "failed"
    simulation_id: str
    prediction: Optional[PredictionCard] = None
    error: Optional[str] = None
    execution_time_seconds: Optional[float] = None
