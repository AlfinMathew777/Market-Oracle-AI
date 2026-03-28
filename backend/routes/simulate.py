"""API route for running market simulations."""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
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

# In-memory store: simulation_id → {status, prediction, error, started_at, ...}
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


@router.post("/simulate")
async def run_simulation(request: Request, body: SimulationRequest, background_tasks: BackgroundTasks):
    """
    POST /api/simulate — starts a background simulation, returns simulation_id immediately.

    The client should poll GET /api/simulate/status/{simulation_id} every 5 seconds.
    When status is 'completed' or 'partial', the prediction field contains the report.
    """
    from server import require_api_key
    require_api_key(request)

    simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

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

    active_simulations[simulation_id] = {
        'status': 'running',
        'started_at': datetime.now().isoformat(),
        'prediction': None,
        'error': None,
    }

    background_tasks.add_task(_run_simulation_background, simulation_id, body, event_data)

    return {
        "status": "started",
        "simulation_id": simulation_id,
    }


async def _run_simulation_background(simulation_id: str, body: SimulationRequest, event_data: dict):
    """
    Runs the full simulation pipeline in the background.
    Stores result (or partial result on timeout) into active_simulations.
    The internal agent budget (180s) and Phase-7 fallback ensure a report always emerges.
    """
    start_time = datetime.now()

    try:
        # Ticker mapping
        if body.affected_tickers and len(body.affected_tickers) > 0:
            ticker = body.affected_tickers[0]
            ticker_confidence = 1.0
            ticker_reasoning = "user-specified"
        else:
            from services.semantic_ticker_mapper import map_event_to_ticker as semantic_mapper
            ticker, ticker_confidence, ticker_reasoning = await asyncio.wait_for(
                semantic_mapper(event_data), timeout=30.0
            )
        event_data["ticker_confidence"] = ticker_confidence
        event_data["ticker_reasoning"] = ticker_reasoning

        ticker_info = get_ticker_info(ticker)
        if not ticker_info:
            active_simulations[simulation_id].update({
                'status': 'failed',
                'error': f"Invalid ticker: {ticker}",
            })
            return

        # Chokepoint context
        try:
            from services.chokepoint_service import get_chokepoint_simulation_context
            event_data["chokepoint_context"] = get_chokepoint_simulation_context()
        except Exception as cp_err:
            logger.warning("Chokepoint context unavailable: %s", cp_err)

        # UTF-8 safety
        import sys, io
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass

        from scripts.test_core import Simulation
        from llm_router import LLMRouter

        llm_router = LLMRouter()
        simulation = Simulation(llm_router)

        # Store ticker so the status endpoint can return it early
        active_simulations[simulation_id]['ticker'] = ticker

        # Run simulation — internal timeouts guarantee completion:
        #   180s agent budget → partial results if slow
        #   60s Phase-7 judge → fallback verdict if slow
        simulation_results = await simulation.run_simulation(
            event_data=event_data,
            ticker=ticker,
            num_rounds=1,
        )

        # Generate report — 60s timeout, fallback on exception
        try:
            prediction = await asyncio.wait_for(
                simulation.generate_prediction_report(simulation_results),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Report generation timed out — using raw simulation results")
            prediction = _build_fallback_prediction(simulation_results, ticker)

        execution_time = (datetime.now() - start_time).total_seconds()

        await _persist_simulation(simulation_id, ticker, prediction, event_data, execution_time)

        # Use model_dump(mode='json') so enums → strings, datetimes → ISO strings.
        # Plain dict from _build_fallback_prediction is already JSON-safe.
        if hasattr(prediction, 'model_dump'):
            prediction_json = prediction.model_dump(mode='json')
        else:
            prediction_json = prediction

        logger.info("=== POLL DEBUG: Storing result for %s ===", simulation_id)
        logger.info("  prediction_json type: %s", type(prediction_json).__name__)
        logger.info("  prediction_json is None: %s", prediction_json is None)
        if prediction_json and isinstance(prediction_json, dict):
            logger.info("  prediction_json keys: %s", list(prediction_json.keys())[:10])
            logger.info("  direction: %s, confidence: %s", prediction_json.get('direction'), prediction_json.get('confidence'))
        elif prediction_json is None:
            logger.error("  *** PREDICTION IS NONE — generate_prediction_report() likely failed ***")
            prediction_json = _build_fallback_prediction(simulation_results, ticker)
            logger.info("  *** Used fallback prediction instead ***")

        active_simulations[simulation_id].update({
            'status': 'completed',
            'prediction': prediction_json,
            'completed_at': datetime.now().isoformat(),
            'execution_time': execution_time,
        })
        logger.info("Simulation %s completed in %.1fs", simulation_id, execution_time)

    except asyncio.TimeoutError:
        # Ticker mapping timed out — nothing to show
        active_simulations[simulation_id].update({
            'status': 'failed',
            'error': 'Ticker mapping timed out — please try again.',
        })
    except Exception as e:
        logger.error("Simulation %s failed: %s", simulation_id, e, exc_info=True)
        active_simulations[simulation_id].update({
            'status': 'failed',
            'error': str(e),
        })


def _build_fallback_prediction(sim_results: dict, ticker: str) -> dict:
    """
    Build a minimal prediction dict from raw simulation results
    when the full report generator times out.
    """
    n_bull = sim_results.get('n_bull', 0)
    n_bear = sim_results.get('n_bear', 0)
    n_neut = sim_results.get('n_neut', 0)
    total = n_bull + n_bear + n_neut or 1

    if n_bull > n_bear:
        direction = 'UP'
    elif n_bear > n_bull:
        direction = 'DOWN'
    else:
        direction = 'NEUTRAL'

    confidence = round(abs(n_bull - n_bear) / total * (1 - n_neut / total), 3)

    return {
        'ticker': ticker,
        'direction': direction,
        'confidence': min(confidence, 0.85),
        'time_horizon': '3d',
        'summary': (
            f"Partial report — {n_bull + n_bear + n_neut} agents completed before timeout. "
            f"Bull: {n_bull} | Bear: {n_bear} | Neutral: {n_neut}."
        ),
        'trigger_event': 'Report generated from partial agent consensus',
        'causal_chain': [],
        'key_signals': [],
        'agent_consensus': {'up': n_bull, 'down': n_bear, 'neutral': n_neut},
        'is_partial': True,
    }


@router.get("/simulate/status/{simulation_id}")
async def get_simulation_status(simulation_id: str):
    """
    Poll this endpoint after POST /api/simulate.
    Returns status + prediction when ready.
    Status values: 'running' | 'completed' | 'failed'
    """
    if simulation_id not in active_simulations:
        logger.warning("POLL DEBUG: %s NOT FOUND (known: %s)", simulation_id, list(active_simulations.keys())[-5:])
        raise HTTPException(status_code=404, detail="Simulation not found")

    entry = active_simulations[simulation_id]
    status = entry.get('status', 'unknown')
    has_prediction = entry.get('prediction') is not None
    logger.info("POLL DEBUG: %s → status=%s, has_prediction=%s", simulation_id, status, has_prediction)

    if status == 'completed' and not has_prediction:
        logger.error("POLL DEBUG: %s is COMPLETED but prediction is None — injecting fallback", simulation_id)
        ticker = entry.get('ticker', 'BHP.AX')
        fallback = _build_fallback_prediction({}, ticker)
        entry['prediction'] = fallback
        active_simulations[simulation_id] = entry

    return entry


@router.get("/simulate/active")
async def list_active_simulations():
    """List all active simulations."""
    return {
        "active_count": sum(1 for s in active_simulations.values() if s['status'] == 'running'),
        "simulations": {k: {kk: vv for kk, vv in v.items() if kk != 'prediction'}
                        for k, v in active_simulations.items()},
    }


@router.post("/simulate/chokepoint")
async def simulate_chokepoint_disruption(chokepoint_id: str, duration_days: int = 7):
    """
    POST /api/simulate/chokepoint?chokepoint_id=malacca&duration_days=7

    Fast prediction for a chokepoint disruption — uses Australian Impact Engine
    directly without running the full 50-agent simulation.
    """
    from services.chokepoint_service import CHOKEPOINTS
    from services.australian_impact_engine import predict_australian_impact

    if chokepoint_id not in CHOKEPOINTS:
        raise HTTPException(status_code=400, detail=f"Unknown chokepoint: {chokepoint_id}")

    try:
        from services.australian_impact_engine import CHOKEPOINT_AUSTRALIA_MATRIX
        impact = predict_australian_impact([chokepoint_id], duration_days)
        cp = CHOKEPOINTS[chokepoint_id]
        matrix_entry = CHOKEPOINT_AUSTRALIA_MATRIX.get(chokepoint_id, {})
        return {
            "status": "completed",
            "chokepoint_id": chokepoint_id,
            "chokepoint_name": cp["name"],
            "chokepoint_details": {
                "oil_flow_mbd": cp.get("oil_flow_mbd"),
                "pct_global_supply": cp.get("pct_global_supply"),
                "risk_level": cp.get("risk_level"),
                "alternative_route": cp.get("alternative_route"),
                "current_threat": cp.get("current_threat"),
                "cargo_types": cp.get("cargo_types", []),
                "countries_controlling": cp.get("countries_controlling", []),
            },
            "sector_impacts": matrix_entry.get("australian_impact", {}),
            "gdp_impact_estimate": matrix_entry.get("gdp_impact_estimate"),
            "impact": impact,
        }
    except Exception as e:
        logger.error("Chokepoint simulation error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


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
    """Save simulation result to SQLite (simulations + prediction_log)."""
    try:
        from database import save_simulation
        await save_simulation(simulation_id, ticker, prediction, event_data, execution_time)
        logger.info("Saved simulation %s to DB", simulation_id)
    except Exception as e:
        logger.error("save_simulation failed for %s: %s", simulation_id, e, exc_info=True)

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

        raw_dir = p.get("direction", "NEUTRAL")
        direction_str = raw_dir.value if hasattr(raw_dir, "value") else str(raw_dir)

        await save_prediction_log(
            simulation_id=simulation_id,
            ticker=ticker,
            direction=direction_str,
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
        logger.info("Saved prediction_log for %s (%s)", simulation_id, ticker)
    except Exception as e:
        logger.error("save_prediction_log failed for %s: %s", simulation_id, e, exc_info=True)
