"""Prediction output schema for Market Oracle AI — v2.

Adds new fields for:
  - Programmatic confidence metadata (confidence_method)
  - Judge agent output (judge_verdict, judge_confidence_modifier)
  - Live market snapshot (iron_ore_price, audusd_rate, brent_price, ticker_rsi)
  - Structured causal chain fields (trigger_event, cost_impact, revenue_impact,
    demand_signal, sentiment_signal)
  - Data freshness timestamp
  - Past accuracy (from prediction_log)

All new fields are Optional to maintain backward compatibility with existing
frontend code that renders confidence, causal_chain, agent_consensus, etc.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


class DirectionEnum(str, Enum):
    UP      = "UP"
    DOWN    = "DOWN"
    NEUTRAL = "NEUTRAL"


class TimeHorizonEnum(str, Enum):
    H24 = "h24"
    D7  = "d7"
    D30 = "d30"


class SignalType(str, Enum):
    CONFLICT         = "conflict"
    COMMODITY        = "commodity"
    MACRO            = "macro"
    SHIPPING         = "shipping"
    MARKET_SENTIMENT = "market_sentiment"


class KeySignal(BaseModel):
    signal_type: SignalType
    description: str
    impact:      str       # "positive" | "negative" | "neutral"
    confidence:  float = Field(ge=0, le=1)


class AgentConsensus(BaseModel):
    up:      int = Field(ge=0)
    down:    int = Field(ge=0)
    neutral: int = Field(ge=0)

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
    step:        int
    event:       str   # label / category (e.g. "DIRECT COST IMPACT")
    consequence: str   # the actual text


class PredictionCard(BaseModel):
    """Complete prediction output — single source of truth for prediction JSON schema."""

    # ── Core prediction ───────────────────────────────────────────────────────
    ticker:       str
    direction:    DirectionEnum
    confidence:   float = Field(ge=0, le=1, description="Programmatically calculated confidence (0-1)")
    time_horizon: TimeHorizonEnum = Field(default=TimeHorizonEnum.D7)

    # ── Causal chain (structured 6-step format from Judge) ────────────────────
    causal_chain: List[CausalChainStep] = Field(min_length=2, max_length=6)

    # ── Key signals ───────────────────────────────────────────────────────────
    key_signals: List[KeySignal] = Field(min_length=1)

    # ── Agent consensus ───────────────────────────────────────────────────────
    agent_consensus: AgentConsensus

    # ── Metadata ──────────────────────────────────────────────────────────────
    simulation_id:    str
    trigger_event_id: Optional[str]    = None
    generated_at:     datetime         = Field(default_factory=datetime.utcnow)

    # ── Optional narrative fields ─────────────────────────────────────────────
    contrarian_view: Optional[str]       = None
    risk_factors:    Optional[List[str]] = None

    # ── UPGRADE 6: New fields ─────────────────────────────────────────────────

    # Confidence provenance
    confidence_method:         Optional[str] = Field(
        default="weighted_variance_v2",
        description="Always 'weighted_variance_v2' — confidence is never LLM-generated"
    )

    # Judge output
    judge_verdict:             Optional[str] = None   # "bullish" | "bearish" | "neutral"
    judge_confidence_modifier: Optional[int] = None   # +10 | 0 | -10

    # Live market snapshot (at time of prediction)
    iron_ore_price:    Optional[float] = None
    iron_ore_change_pct: Optional[float] = None
    audusd_rate:       Optional[float] = None
    audusd_change_pct: Optional[float] = None
    brent_price:       Optional[float] = None
    ticker_price:      Optional[float] = None
    ticker_rsi:        Optional[float] = None

    # Structured causal chain fields (flat, from Judge)
    trigger_event:    Optional[str] = None
    cost_impact:      Optional[str] = None
    revenue_impact:   Optional[str] = None
    demand_signal:    Optional[str] = None
    sentiment_signal: Optional[str] = None

    # Data freshness
    data_freshness: Optional[str] = None   # ISO timestamp of market data fetch

    # Rolling accuracy from prediction_log (if available)
    past_accuracy: Optional[float] = None  # % correct, e.g. 0.67

    # Bug Fix 5: Data quality fields
    data_quality:      Optional[str]       = None  # "GOOD" | "PARTIAL" | "POOR"
    data_issues:       Optional[List[str]] = None  # list of issue descriptions
    show_data_warning: Optional[bool]      = None  # True when data_quality == "POOR"

    # Fix 2: Broad market session warning
    market_warning:    Optional[str]       = None  # e.g. "CONTRARIAN: broad selloff detected..."

    # Judge logic override flag (two-stage judge pipeline)
    override_flag:     Optional[str]       = None  # e.g. "LOGIC_OVERRIDE: agent majority overridden"

    # Fix 1: Minimum confidence guard
    signal_note:       Optional[str]       = None  # "INSUFFICIENT_SIGNAL: ..." or None

    # Fix 2: Causal chain audit
    chain_override_flag: Optional[str]     = None  # "CHAIN_OVERRIDE: ..." or "CHAIN_CONFIRMED: ..."
    slot_verdicts:     Optional[dict]      = None  # {"cost": "bearish", "revenue": "bearish", ...}

    # Fix 3: Stale news transparency
    stale_news_dropped: Optional[int]      = None  # count of news items dropped by date filter

    # Fix 4: Blind judge + reconciler detail fields
    blind_judge_verdict:    Optional[str]  = None  # "bullish" | "bearish" | "neutral"
    blind_judge_confidence: Optional[str]  = None  # "high" | "medium" | "low"
    blind_judge_reasoning:  Optional[str]  = None
    reconciler_flag:        Optional[str]  = None  # "LOGIC_OVERRIDE" | "VOTES_HELD_LOW_LOGIC" | ...
    reconciler_reasoning:   Optional[str]  = None

    # Trend Momentum fields
    trend_label:             Optional[str]   = None  # "STRONG_DOWNTREND" | "DOWNTREND" | "NEUTRAL" | "UPTREND" | "STRONG_UPTREND"
    day_1_change:            Optional[float] = None  # 1-day return %
    day_5_change:            Optional[float] = None  # 5-day return %
    day_20_change:           Optional[float] = None  # 20-day return %
    consecutive_down_days:   Optional[int]   = None  # consecutive sessions closed lower
    dist_from_52w_high_pct:  Optional[float] = None  # % distance from 52-week high (negative = below)
    ticker_volume_vs_avg:    Optional[float] = None  # intraday volume / 3-month avg volume

    # Trend data provenance — shown in UI when data is not freshly fetched
    trend_from_cache:        Optional[bool]  = None  # True when trend came from cache (not live fetch)
    trend_emergency:         Optional[bool]  = None  # True when hardcoded emergency fallback was used
    trend_cache_age_hours:   Optional[float] = None  # How old the cache entry was (hours)

    # Anti-bias transparency
    persona_distribution:    Optional[str]   = None  # e.g. "Bear-weighted: strong downtrend confirmed"

    # Polymarket prediction market signals at time of simulation
    polymarket_markets:      Optional[List[dict]] = None  # top relevant markets with odds

    model_config = {
        "json_schema_extra": {
            "example": {
                "ticker":     "BHP.AX",
                "direction":  "DOWN",
                "confidence": 0.23,
                "confidence_method": "weighted_variance_v2",
                "judge_verdict": "bearish",
                "judge_confidence_modifier": -10,
                "time_horizon": "d7",
                "iron_ore_price": 95.2,
                "iron_ore_change_pct": -1.8,
                "audusd_rate": 0.6480,
                "brent_price": 81.0,
                "ticker_rsi": 44.2,
                "trigger_event": "China announces 15% iron ore import quota cut, Mar 2026, Xinhua",
                "cost_impact": "No direct cost impact — energy prices stable ➡️",
                "revenue_impact": "Iron ore export volumes fall 15% → BHP revenue down ~$2.1B annually ⬇️",
                "demand_signal": "China steel mills reduce orders → Port Hedland throughput falls ⬇️",
                "sentiment_signal": "Risk-off: AUD/USD falls, iron ore futures -3.2% ⬇️",
                "causal_chain": [
                    {"step": 1, "event": "TRIGGER EVENT", "consequence": "China iron ore quota cut"},
                    {"step": 2, "event": "DIRECT COST IMPACT", "consequence": "No direct cost impact ➡️"},
                    {"step": 3, "event": "DIRECT REVENUE IMPACT", "consequence": "Export volumes fall ⬇️"},
                    {"step": 4, "event": "DEMAND SIGNAL", "consequence": "Chinese mill orders fall ⬇️"},
                    {"step": 5, "event": "SENTIMENT SIGNAL", "consequence": "Risk-off, AUD/USD falls ⬇️"},
                    {"step": 6, "event": "NET CONCLUSION", "consequence": "Overall direction: DOWN ⬇️"},
                ],
                "agent_consensus": {"up": 0, "down": 24, "neutral": 26},
                "simulation_id": "sim_20260320_001",
                "generated_at": "2026-03-20T10:30:00Z",
            }
        }
    }


class SimulationRequest(BaseModel):
    event_id:       Optional[str]  = None
    event_data:     Optional[dict] = None
    ticker_override: Optional[str] = None


class SimulationResponse(BaseModel):
    status:                  str
    simulation_id:           str
    prediction:              Optional[PredictionCard] = None
    error:                   Optional[str]            = None
    execution_time_seconds:  Optional[float]          = None
