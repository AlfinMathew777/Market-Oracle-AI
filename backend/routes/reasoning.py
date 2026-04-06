"""
Reasoning Synthesizer API Endpoint — Full Integration
------------------------------------------------------
Wires together: memory injection → synthesis → trade execution →
accuracy tracking → WebSocket broadcast in a single call.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from middleware.auth import verify_api_key
from middleware.rate_limit import llm_rate_limit, rate_limiter

from agents.reasoning_synthesizer import ReasoningSynthesizer
from agents.prediction_memory import PredictionMemory
from agents.trade_executor import TradeExecutor
from llm_router import LLMRouter
from models.reasoning_output import ReasoningOutput
from models.trade_execution import TradeExecution, TradeExecutionRequest
from services.accuracy_tracker import store_prediction
from services.realtime_stream import stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reasoning", tags=["reasoning"])

# Module-level singleton (stateless, safe to share across requests)
_llm_router: Optional[LLMRouter] = None


def _get_llm_router() -> LLMRouter:
    global _llm_router
    if _llm_router is None:
        _llm_router = LLMRouter()
    return _llm_router


# ── Request / Response models ─────────────────────────────────────────────────

class ReasoningRequest(BaseModel):
    stock_ticker: str = Field(..., example="BHP.AX")
    news_headline: str = Field(..., example="China announces infrastructure stimulus")
    news_summary: str = Field(
        ...,
        example="Beijing unveils $140B infrastructure spending plan targeting steel-intensive construction",
    )
    market_signals: Dict[str, Any] = Field(
        default_factory=dict,
        example={
            "current_price": 45.50,
            "iron_ore_62fe": 118.5,
            "aud_usd": 0.652,
            "atr_14": 1.25,
            "rsi_14": 52,
            "ma_20": 44.80,
            "ma_50": 43.50,
            "ma_200": 42.00,
            "support_levels": [44.00, 43.00, 42.00],
            "resistance_levels": [46.00, 47.50, 49.00],
        },
    )
    agent_votes: Dict[str, int] = Field(
        default_factory=lambda: {"bullish": 0, "bearish": 0, "neutral": 0},
        example={"bullish": 28, "bearish": 8, "neutral": 9},
    )
    data_provenance: Dict[str, Any] = Field(default_factory=dict)

    # Feature toggles
    generate_trade_execution: bool = Field(True, description="Generate trade levels for BUY/SELL signals")
    use_memory: bool = Field(True, description="Inject historical prediction memory into the prompt")
    broadcast_signal: bool = Field(True, description="Broadcast new signal via WebSocket")
    risk_tolerance: str = Field("moderate", description="conservative | moderate | aggressive")


class ReasoningResponse(BaseModel):
    success: bool
    timestamp: str
    stock_ticker: str

    # Core prediction
    prediction: ReasoningOutput

    # Trade execution plan (if generated)
    trade_execution: Optional[TradeExecution] = None

    # Accuracy tracking
    prediction_id: Optional[str] = None

    # Memory context used
    memory_applied: bool = False
    memory_summary: Optional[str] = None

    # Broadcast
    signal_broadcast: bool = False

    processing_time_ms: float


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/synthesize", response_model=ReasoningResponse)
async def synthesize_reasoning(
    request: ReasoningRequest,
    http_request: Request,
    api_key: str = Depends(verify_api_key),
    rate_info: dict = Depends(llm_rate_limit),
) -> ReasoningResponse:
    """
    Full prediction pipeline in one call:
    1. Inject historical memory context into the LLM prompt (optional)
    2. Run the 8-step Reasoning Synthesizer
    3. Generate trade execution levels for actionable signals (optional)
    4. Store prediction for accuracy tracking
    5. Broadcast signal via WebSocket (optional)
    """
    start = datetime.now(timezone.utc)

    # ── Step 1: initialise memory (lazy, no-op if DB is cold) ─────────────────
    memory: Optional[PredictionMemory] = None
    if request.use_memory:
        try:
            memory = PredictionMemory()
        except Exception as exc:
            logger.warning("PredictionMemory init failed — continuing without: %s", exc)

    # ── Step 2: synthesize ────────────────────────────────────────────────────
    synthesizer = ReasoningSynthesizer(_get_llm_router(), prediction_memory=memory)
    try:
        result = await synthesizer.synthesize(
            stock_ticker=request.stock_ticker,
            news_headline=request.news_headline,
            news_summary=request.news_summary,
            market_signals=request.market_signals,
            agent_votes=request.agent_votes,
            data_provenance=request.data_provenance,
            inject_memory=request.use_memory,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reasoning synthesis failed: {exc}") from exc

    memory_ctx = result.memory_context
    memory_applied = bool(memory_ctx and memory_ctx.get("has_memory"))
    memory_summary: Optional[str] = None
    if memory_applied and memory_ctx:
        memory_summary = memory_ctx.get("memory_prompt", "")[:200] or None

    # ── Step 3: trade execution ───────────────────────────────────────────────
    trade_execution: Optional[TradeExecution] = None
    if (
        request.generate_trade_execution
        and result.final_decision.recommendation.value in ("BUY", "SELL")
        and request.market_signals.get("current_price")
    ):
        try:
            trade_request = TradeExecutionRequest(
                prediction_id="placeholder",  # replaced after store
                stock_ticker=request.stock_ticker,
                current_price=float(request.market_signals["current_price"]),
                direction=result.final_decision.direction.value.upper(),
                recommendation=result.final_decision.recommendation.value,
                confidence_score=result.final_decision.confidence_score,
                risk_tolerance=request.risk_tolerance,
                atr_14=request.market_signals.get("atr_14"),
                support_levels=request.market_signals.get("support_levels", []),
                resistance_levels=request.market_signals.get("resistance_levels", []),
                ma_20=request.market_signals.get("ma_20"),
                ma_50=request.market_signals.get("ma_50"),
                ma_200=request.market_signals.get("ma_200"),
                rsi_14=request.market_signals.get("rsi_14"),
                vwap=request.market_signals.get("vwap"),
            )
            trade_execution = TradeExecutor().generate_execution_plan(trade_request)
        except Exception as exc:
            logger.error("Trade execution failed for %s: %s", request.stock_ticker, exc)

    # ── Step 4: store prediction ──────────────────────────────────────────────
    prediction_id: Optional[str] = None
    try:
        current_price = float(request.market_signals.get("current_price", 0))
        prediction_id = await store_prediction(
            reasoning_output=result,
            current_price=current_price,
            trade_execution=trade_execution,
        )
        # Backfill prediction_id into trade execution object
        if trade_execution and prediction_id:
            trade_execution.prediction_id = prediction_id
    except Exception as exc:
        logger.error("Failed to store prediction for %s: %s", request.stock_ticker, exc)

    # ── Step 5: broadcast ─────────────────────────────────────────────────────
    signal_broadcast = False
    if request.broadcast_signal:
        try:
            await stream_manager.broadcast_signal(
                ticker=request.stock_ticker,
                signal={
                    "prediction_id": prediction_id,
                    "direction": result.final_decision.direction.value,
                    "recommendation": result.final_decision.recommendation.value,
                    "confidence": result.final_decision.confidence_score,
                    "risk_level": result.final_decision.risk_level.value,
                    "entry_price": trade_execution.entry_price if trade_execution else None,
                    "stop_loss": trade_execution.stop_loss if trade_execution else None,
                    "take_profit_1": trade_execution.take_profit_1 if trade_execution else None,
                    "setup_quality": trade_execution.setup_quality if trade_execution else None,
                },
            )
            signal_broadcast = True
        except Exception as exc:
            logger.error("WebSocket broadcast failed for %s: %s", request.stock_ticker, exc)

    elapsed_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

    return ReasoningResponse(
        success=True,
        timestamp=datetime.now(timezone.utc).isoformat(),
        stock_ticker=request.stock_ticker,
        prediction=result,
        trade_execution=trade_execution,
        prediction_id=prediction_id,
        memory_applied=memory_applied,
        memory_summary=memory_summary,
        signal_broadcast=signal_broadcast,
        processing_time_ms=round(elapsed_ms, 2),
    )


@router.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "reasoning_synthesizer",
        "auth_required": True,
        "rate_limit": "10 requests/minute",
        "features": {
            "memory_integration": True,
            "trade_execution": True,
            "accuracy_tracking": True,
            "websocket_broadcast": True,
        },
    }
