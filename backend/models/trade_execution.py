"""
Trade Execution Models
----------------------
Defines actionable trade parameters including entry, exit, and risk levels.
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from enum import Enum
from datetime import datetime, timezone


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    WAIT = "WAIT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LIMIT = "STOP_LIMIT"


class TradeTimeframe(str, Enum):
    SCALP = "SCALP"
    INTRADAY = "INTRADAY"
    SWING = "SWING"
    POSITION = "POSITION"


class RiskRewardProfile(BaseModel):
    risk_amount: float = Field(..., description="Distance from entry to stop-loss in $")
    reward_amount: float = Field(..., description="Distance from entry to take-profit in $")
    risk_reward_ratio: float = Field(..., description="Reward / Risk ratio")
    risk_percent: float = Field(..., description="Risk as % of entry price")

    @model_validator(mode="after")
    def calculate_rr(self) -> "RiskRewardProfile":
        if self.risk_amount > 0:
            self.risk_reward_ratio = round(self.reward_amount / self.risk_amount, 2)
        return self


class PriceLevel(BaseModel):
    price: float
    rationale: str
    level_type: Literal["support", "resistance", "fibonacci", "vwap", "ma", "custom"]


class TradeExecution(BaseModel):
    """Complete trade execution plan with entry, exit, and risk parameters."""

    # Identification
    stock_ticker: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime
    prediction_id: str

    # Action
    action: TradeAction
    order_type: OrderType = OrderType.LIMIT
    timeframe: TradeTimeframe

    # Price Levels
    current_price: float
    entry_price: float
    entry_zone_low: float
    entry_zone_high: float

    # Exit Levels
    stop_loss: float
    stop_loss_rationale: str
    take_profit_1: float
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None

    # Risk Management
    risk_reward: RiskRewardProfile
    position_size_percent: float = Field(..., ge=0.5, le=5.0)
    max_loss_percent: float

    # Key Levels
    key_support_levels: list[PriceLevel] = Field(default_factory=list)
    key_resistance_levels: list[PriceLevel] = Field(default_factory=list)

    # Conditions
    entry_conditions: list[str]
    invalidation_conditions: list[str]

    # Confidence
    setup_quality: Literal["A+", "A", "B", "C"]
    confidence_score: int = Field(..., ge=0, le=100)
    notes: Optional[str] = None


class TradeExecutionRequest(BaseModel):
    """Request to generate a trade execution plan from a prediction signal."""
    prediction_id: str
    stock_ticker: str
    current_price: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    recommendation: Literal["BUY", "SELL", "HOLD", "WAIT"]
    confidence_score: int = Field(..., ge=0, le=100)
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = "moderate"
    account_size: Optional[float] = None

    # Technical context
    atr_14: Optional[float] = Field(None, description="14-period ATR")
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    ma_20: Optional[float] = None
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None
    rsi_14: Optional[float] = None
    vwap: Optional[float] = None
