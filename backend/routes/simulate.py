"""API route for running market simulations."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import asyncio
import logging
from datetime import datetime
import uuid

from models.prediction import PredictionCard, SimulationResponse
from event_ticker_mapping import map_event_to_ticker, get_ticker_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["simulation"])

# Store active simulations
active_simulations = {}


def _get_limiter():
    """Lazy import to avoid circular dependency with server.py."""
    from server import limiter, require_api_key
    return limiter, require_api_key


class SimulationRequest(BaseModel):
    """Request body for POST /api/simulate."""
    event_id: Optional[str] = None
    event_description: str
    event_type: str
    lat: float
    lon: float
    country: str = "Unknown"
    fatalities: int = 0
    affected_tickers: Optional[List[str]] = None
    date: Optional[str] = None

    @field_validator('lat')
    @classmethod
    def validate_lat(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('lat must be between -90 and 90')
        return v

    @field_validator('lon')
    @classmethod
    def validate_lon(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('lon must be between -180 and 180')
        return v

    @field_validator('fatalities')
    @classmethod
    def validate_fatalities(cls, v):
        if v < 0:
            raise ValueError('fatalities cannot be negative')
        return v

    @field_validator('event_description', 'event_type', 'country')
    @classmethod
    def strip_and_limit(cls, v):
        v = v.strip()[:500]
        if not v:
            raise ValueError('field cannot be empty')
        return v


def _get_limiter_decorator():
    from server import limiter
    return limiter.limit("5/minute")

@router.post("/simulate")
async def run_simulation(request: Request, body: SimulationRequest):
    """
    POST /api/simulate — rate-limited to 5/minute per IP; requires API key when configured.

    Runs 50-agent simulation for a conflict event to predict ASX ticker impact.
    Timeout: 360 seconds (6 minutes) to cover 3-5 minute simulation time.
    """
    # Enforce API key (no-op when API_KEY env var is not set)
    from server import require_api_key
    require_api_key(request)

    simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    try:
        logger.info(f"Starting simulation {simulation_id}")
        logger.info(f"Event: {body.country} - {body.event_type}")

        # Mark simulation as running
        active_simulations[simulation_id] = {
            'status': 'running',
            'started_at': datetime.now().isoformat()
        }
        
        # Build event data for mapping
        event_data = {
            'country': body.country,
            'location': body.event_description,
            'event_type': body.event_type,
            'fatalities': body.fatalities,
            'event_date': body.date or datetime.now().strftime('%Y-%m-%d'),
            'notes': body.event_description,
            'latitude': body.lat,
            'longitude': body.lon,
            'event_id_cnty': body.event_id or f"evt_{simulation_id}"
        }

        # Map event to ticker — semantic (Zep) with rule-based fallback
        if body.affected_tickers and len(body.affected_tickers) > 0:
            ticker = body.affected_tickers[0]
            ticker_confidence = 1.0
            ticker_reasoning  = "user-specified"
            logger.info(f"Using provided ticker: {ticker}")
        else:
            from services.semantic_ticker_mapper import map_event_to_ticker as semantic_mapper
            ticker, ticker_confidence, ticker_reasoning = await semantic_mapper(event_data)
            logger.info(
                f"Ticker mapped: {ticker} (confidence={ticker_confidence:.2f}, {ticker_reasoning})"
            )
        event_data["ticker_confidence"] = ticker_confidence
        event_data["ticker_reasoning"]  = ticker_reasoning
        
        ticker_info = get_ticker_info(ticker)
        if not ticker_info:
            raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
        
        # Run simulation (this is the Phase 1 simulation engine)
        start_time = datetime.now()

        # Inject live chokepoint context into event data
        try:
            from services.chokepoint_service import get_chokepoint_simulation_context
            chokepoint_context = get_chokepoint_simulation_context()
            event_data["chokepoint_context"] = chokepoint_context
            logger.info("Chokepoint context injected into simulation")
        except Exception as cp_err:
            logger.warning(f"Chokepoint context unavailable: {cp_err}")

        # Import simulation components
        from scripts.test_core import Simulation
        from llm_router import LLMRouter

        # Ensure stdout/stderr use UTF-8 so LLM responses with unicode don't crash
        import sys, io
        if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        elif hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass
        if hasattr(sys.stderr, 'buffer') and not isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        elif hasattr(sys.stderr, 'reconfigure'):
            try:
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass

        llm_router = LLMRouter()
        simulation = Simulation(llm_router)

        # Run simulation with timeout protection
        try:
            # Use asyncio.wait_for with 360 second timeout
            simulation_results = await asyncio.wait_for(
                simulation.run_simulation(
                    event_data=event_data,
                    ticker=ticker,
                    num_rounds=3  # 3 rounds for MVP speed
                ),
                timeout=360.0  # 6 minutes max
            )
            
            # Generate prediction report
            prediction = await asyncio.wait_for(
                simulation.generate_prediction_report(simulation_results),
                timeout=60.0  # 1 minute for report generation
            )
            
            execution_time = (datetime.now() - start_time).total_seconds()

            # Persist to SQLite (non-blocking — doesn't slow the response)
            asyncio.create_task(
                _persist_simulation(simulation_id, ticker, prediction, event_data, execution_time)
            )

            # Update simulation status
            active_simulations[simulation_id] = {
                'status': 'completed',
                'started_at': start_time.isoformat(),
                'completed_at': datetime.now().isoformat(),
                'execution_time': execution_time
            }

            logger.info(f"Simulation {simulation_id} completed in {execution_time:.1f}s")

            return SimulationResponse(
                status="completed",
                simulation_id=simulation_id,
                prediction=prediction,
                execution_time_seconds=execution_time
            )
            
        except asyncio.TimeoutError:
            logger.error(f"Simulation {simulation_id} timed out after 360 seconds")
            active_simulations[simulation_id]['status'] = 'timeout'
            raise HTTPException(
                status_code=504,
                detail="Simulation timed out. This may happen under heavy load. Please try again."
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in simulation {simulation_id}: {str(e)}", exc_info=True)
        active_simulations[simulation_id] = {
            'status': 'failed',
            'error': str(e)
        }
        raise HTTPException(
            status_code=500,
            detail=f"Simulation failed: {str(e)}"
        )


@router.post("/simulate/chokepoint")
async def simulate_chokepoint_disruption(chokepoint_id: str, duration_days: int = 7):
    """
    POST /api/simulate/chokepoint?chokepoint_id=malacca&duration_days=7

    Fast prediction for a chokepoint disruption ? uses Australian Impact Engine
    directly without running the full 50-agent simulation. Returns ASX predictions
    and export value at risk within seconds.
    """
    from services.chokepoint_service import CHOKEPOINTS
    from services.australian_impact_engine import predict_australian_impact

    if chokepoint_id not in CHOKEPOINTS:
        raise HTTPException(status_code=400, detail=f"Unknown chokepoint: {chokepoint_id}")

    try:
        impact = predict_australian_impact([chokepoint_id], duration_days)
        cp = CHOKEPOINTS[chokepoint_id]
        return {
            "status": "completed",
            "chokepoint_id": chokepoint_id,
            "chokepoint_name": cp["name"],
            "impact": impact,
            "prediction": {
                "direction": impact["asx_predictions"][0]["direction"] if impact["asx_predictions"] else "NEUTRAL",
                "key_insight": impact["key_insight"],
                "export_value_at_risk_aud_bn": impact["export_value_at_risk_aud_bn"],
                "top_tickers": [p["ticker"] for p in impact["asx_predictions"][:5]],
                "simulation_seed": impact["simulation_seed"],
            },
        }
    except Exception as e:
        logger.error(f"Chokepoint simulation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/simulate/status/{simulation_id}")
async def get_simulation_status(simulation_id: str):
    """Get status of a running simulation."""
    if simulation_id not in active_simulations:
        raise HTTPException(status_code=404, detail="Simulation not found")
    
    return active_simulations[simulation_id]


@router.get("/simulate/active")
async def list_active_simulations():
    """List all active simulations."""
    return {
        "active_count": sum(1 for s in active_simulations.values() if s['status'] == 'running'),
        "simulations": active_simulations
    }


@router.get("/predict/history")
async def get_prediction_history(ticker: str = None, limit: int = 50):
    """GET /api/predict/history?ticker=BHP.AX&limit=50 — persisted prediction results."""
    from database import get_prediction_history
    rows = await get_prediction_history(ticker=ticker, limit=min(limit, 200))
    return {"status": "success", "data": rows, "count": len(rows)}


@router.get("/predict/accuracy")
async def get_prediction_accuracy(ticker: str = None):
    """GET /api/predict/accuracy?ticker=BHP.AX — rolling accuracy statistics."""
    from database import get_accuracy_stats
    stats = await get_accuracy_stats(ticker=ticker)
    return {"status": "success", "data": stats}


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _persist_simulation(simulation_id, ticker, prediction, event_data, execution_time):
    """Background task: save simulation result to SQLite (simulations + prediction_log)."""
    try:
        from database import save_simulation
        await save_simulation(simulation_id, ticker, prediction, event_data, execution_time)
    except Exception as e:
        logger.warning("Simulation persistence failed (non-critical): %s", e)

    try:
        from database import save_prediction_log
        p = prediction if isinstance(prediction, dict) else prediction.model_dump()
        causal = p.get("causal_chain") or []
        primary_reason = (
            p.get("trigger_event")
            or (causal[0].get("consequence") if causal and isinstance(causal[0], dict) else "")
            or ""
        )
        consensus = p.get("agent_consensus") or {}
        if hasattr(consensus, "up"):
            bull, bear, neut = consensus.up, consensus.down, consensus.neutral
        elif isinstance(consensus, dict):
            bull = consensus.get("up", 0)
            bear = consensus.get("down", 0)
            neut = consensus.get("neutral", 0)
        else:
            bull = bear = neut = 0
        await save_prediction_log(
            simulation_id=simulation_id,
            ticker=ticker,
            direction=p.get("direction", "NEUTRAL"),
            confidence=float(p.get("confidence", 0.0)),
            primary_reason=primary_reason,
            market_ctx={
                "iron_ore_price": p.get("iron_ore_price"),
                "audusd_rate":    p.get("audusd_rate"),
                "brent_price":    p.get("brent_price"),
                "ticker_price":   p.get("ticker_price"),
            },
            agent_bullish=bull,
            agent_bearish=bear,
            agent_neutral=neut,
            trend_label=p.get("trend_label"),
        )
    except Exception as e:
        logger.warning("prediction_log save failed (non-critical): %s", e)
