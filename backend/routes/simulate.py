"""API route for running market simulations."""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import asyncio
import logging
import os
from datetime import datetime
import uuid

from models.prediction import PredictionCard, SimulationResponse
from event_ticker_mapping import map_event_to_ticker, get_ticker_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["simulation"])

# In-memory store: simulation_id → {status, prediction, error, started_at, ...}
active_simulations = {}

# ── Pre-flight commentary filter ──────────────────────────────────────────────
# These patterns in the trigger indicate a stock commentary / opinion article,
# NOT a real market-moving event. Matches → skip the simulation immediately.
_COMMENTARY_PATTERNS: List[str] = [
    # Listicle / watchlist / picks
    "stocks to watch", "shares to watch", "shares to dig into", "stocks to dig into",
    "top picks", "best picks", "analyst picks", "my top", "portfolio picks",
    "investment ideas", "3 reasons", "2 asx shares", "asx shares to", "asx share to",
    "top 10", "5 best", "10 best",
    # Opinion / commentary
    "opinion:", "commentary:", "my view on", "why i think", "i think",
    "in my opinion", "my take on",
    # Valuation / educational
    "easy way to", "how to value", "valuing shares", "valuing asx",
    "how to invest in", "beginner's guide", "beginner guide",
    "how to read", "valuation method", "price-to-earnings", "fair value of",
    "intrinsic value of", "undervalued or overvalued", "explained:",
    # Should you / is it worth
    "should you buy", "worth buying", "worth watching", "on my watchlist",
    "is this a buy", "is it time to buy", "should i buy", "is it worth",
    # Comparison
    "comparing ", " vs ", " versus ", "compared to", "which is better",
    # Deep dive / closer look
    "deep dive into", "deep dive on", "closer look at", "look at why",
    "a closer look", "case for buying", "case against buying",
    # History / background
    "history of", "what is ", "who is ", "about this company",
]


def pre_flight_trigger_check(
    event_description: str,
    event_type: str = "",
) -> tuple:
    """
    Pure-Python pre-flight check (~0ms) — no LLM, no agents.

    Rejects commentary / opinion articles before ANY simulation work begins.
    Called directly in the route handler so a skipped response returns in < 50ms.

    Returns:
        (should_skip: bool, reason: str | None)
    """
    text = f"{event_description} {event_type}".lower()
    for pattern in _COMMENTARY_PATTERNS:
        if pattern in text:
            return True, (
                f"Pre-flight filter blocked: trigger matches commentary pattern "
                f"'{pattern}'. No material market catalyst — simulation skipped."
            )
    return False, None


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

    # ── Pre-flight check (< 1ms, no LLM) ────────────────────────────────────
    _skip, _skip_reason = pre_flight_trigger_check(body.event_description, body.event_type)
    if _skip:
        logger.info("Pre-flight blocked [%s]: %s", simulation_id, _skip_reason)
        return {
            "status": "skipped",
            "simulation_id": simulation_id,
            "reason": _skip_reason,
            "prediction": {
                "ticker": body.affected_tickers[0] if body.affected_tickers else "N/A",
                "direction": "NEUTRAL",
                "confidence": 0.0,
                "time_horizon": "N/A",
                "summary": _skip_reason,
                "trigger_event": body.event_description,
                "causal_chain": [],
                "key_signals": [],
                "agent_consensus": {"up": 0, "down": 0, "neutral": 0},
                "is_skipped": True,
            },
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

    # ── Accuracy gate: mark low-accuracy mode if system is underperforming ──────
    # When we have ≥10 resolved predictions AND accuracy < 40%, the system is not
    # reliable enough to output actionable signals.  We don't abort the simulation;
    # instead we tag event_data so the signal filter can apply stricter thresholds.
    try:
        from database import get_detailed_accuracy_stats
        _acc_stats = await get_detailed_accuracy_stats(ticker=None)
        _resolved  = _acc_stats.get("resolved_predictions", 0) or 0
        _accuracy  = _acc_stats.get("direction_accuracy_pct", 50) or 50
        if _resolved >= 10 and _accuracy < 40:
            event_data["_low_accuracy_mode"]  = True
            event_data["_accuracy_warning"]   = (
                f"System accuracy {_accuracy:.0f}% < 40% threshold — "
                f"signals are non-actionable until accuracy improves"
            )
            logger.warning(
                "Low accuracy mode active: %.0f%% accuracy over %d predictions",
                _accuracy, _resolved,
            )
    except Exception as _gate_err:
        logger.debug("Accuracy gate check failed (non-fatal): %s", _gate_err)

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
        _t_sim_start = datetime.now()
        simulation_results = await simulation.run_simulation(
            event_data=event_data,
            ticker=ticker,
            num_rounds=1,
        )
        _t_sim_end = datetime.now()

        # Generate report — 60s timeout, fallback on exception
        _t_report_start = datetime.now()
        try:
            prediction = await asyncio.wait_for(
                simulation.generate_prediction_report(simulation_results),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Report generation timed out — using raw simulation results")
            prediction = _build_fallback_prediction(simulation_results, ticker)
        _t_report_end = datetime.now()

        execution_time = (datetime.now() - start_time).total_seconds()

        # Phase timing breakdown — check logs to verify optimization impact
        _debug_timings = os.environ.get("DEBUG_TIMINGS", "false").lower() == "true"
        _timings = {
            "data_fetch_s":  (_t_sim_start - start_time).total_seconds(),
            "simulation_s":  (_t_sim_end - _t_sim_start).total_seconds(),
            "report_gen_s":  (_t_report_end - _t_report_start).total_seconds(),
            "total_s":       execution_time,
        }
        if _debug_timings:
            logger.info("Simulation timings %s: %s", simulation_id, _timings)
        else:
            logger.info(
                "Simulation %s timing — fetch=%.1fs sim=%.1fs report=%.1fs total=%.1fs",
                simulation_id,
                _timings["data_fetch_s"], _timings["simulation_s"],
                _timings["report_gen_s"], _timings["total_s"],
            )

        await _persist_simulation(simulation_id, ticker, prediction, event_data, execution_time)

        # Use model_dump(mode='json') so enums → strings, datetimes → ISO strings.
        # Plain dict from _build_fallback_prediction is already JSON-safe.
        if hasattr(prediction, 'model_dump'):
            prediction_json = prediction.model_dump(mode='json')
        else:
            prediction_json = prediction

        if prediction_json is None:
            logger.error("Prediction is None — using fallback for %s", simulation_id)
            prediction_json = _build_fallback_prediction(simulation_results, ticker)

        # Inject CVaR risk_analysis if monte_carlo ran but risk_analysis is missing
        if isinstance(prediction_json, dict):
            mc = prediction_json.get('monte_carlo_price')
            if isinstance(mc, dict) and mc.get('current_price') and 'risk_analysis' not in mc:
                try:
                    import math
                    from services.game_theory.cvar_optimizer import CVaROptimizer
                    curr = float(mc['current_price'])
                    hi = float(mc.get('range_90pct_high') or curr * 1.10)
                    lo = float(mc.get('range_90pct_low') or curr * 0.90)
                    # Estimate daily volatility from 90% CI (≈ 2 × 1.645 × σ × √7)
                    daily_vol = max((hi - lo) / curr / (2 * 1.645 * math.sqrt(7)), 0.005)
                    exp_ret_daily = (mc.get('expected_change_pct') or 0.0) / 100 / 7
                    opt = CVaROptimizer(n_scenarios=5000)
                    metrics = opt.simulate_and_calculate(curr, daily_vol, 7, drift=exp_ret_daily)
                    mc['risk_analysis'] = {
                        'var_95': round(metrics.var_95, 2),
                        'cvar_95': round(metrics.cvar_95, 2),
                        'var_99': round(metrics.var_99, 2),
                        'cvar_99': round(metrics.cvar_99, 2),
                        'expected_return': round(metrics.expected_return, 2),
                        'prob_profit': round(metrics.prob_profit, 1),
                        'risk_adjusted_score': round(metrics.risk_adjusted_score, 3),
                        'tail_risk_ratio': round(metrics.tail_risk_ratio, 2),
                        'risk_level': metrics._get_risk_level(),
                        'var_interpretation': (
                            f"95% confident loss won't exceed {abs(round(metrics.var_95, 1))}%"
                        ),
                        'cvar_interpretation': (
                            f"In worst 5% of scenarios, avg loss is {abs(round(metrics.cvar_95, 1))}%"
                        ),
                    }
                    logger.info("CVaR injected for %s (daily_vol=%.2f%%)", ticker, daily_vol * 100)
                except Exception as _cvar_err:
                    logger.warning("CVaR injection failed: %s", _cvar_err)

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

    On 404 (server restarted, in-memory store wiped): attempts DB recovery.
    """
    if simulation_id not in active_simulations:
        # Attempt to recover completed simulation from SQLite (survives server restart)
        try:
            from database import get_simulation_full_json
            recovered = await get_simulation_full_json(simulation_id)
            if recovered:
                logger.info("Recovered simulation %s from DB after restart", simulation_id)
                # Re-hydrate into active_simulations so subsequent polls are fast
                active_simulations[simulation_id] = {
                    "status": "completed",
                    "prediction": recovered,
                    "completed_at": recovered.get("generated_at"),
                    "recovered": True,
                }
                return active_simulations[simulation_id]
        except Exception as _rec_err:
            logger.warning("DB recovery failed for %s: %s", simulation_id, _rec_err)

        logger.warning("Simulation %s not found (known: %s)", simulation_id, list(active_simulations.keys())[-5:])
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
                "status": cp.get("status"),
                "threat_level": cp.get("threat_level"),
                "alternative_route": cp.get("alternative_route"),
                "current_threat": cp.get("current_threat"),
                "cargo_types": cp.get("cargo_types", []),
                "countries_controlling": cp.get("countries_controlling", []),
                "ceasefire": cp.get("ceasefire"),
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
