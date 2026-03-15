"""API route for running market simulations."""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
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


@router.post("/simulate")
async def run_simulation(request: SimulationRequest):
    """
    POST /api/simulate
    
    Runs 50-agent simulation for a conflict event to predict ASX ticker impact.
    Timeout: 360 seconds (6 minutes) to cover 3-5 minute simulation time.
    
    Args:
        request: SimulationRequest with event data
    
    Returns:
        SimulationResponse with PredictionCard
    """
    simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    try:
        logger.info(f"Starting simulation {simulation_id}")
        logger.info(f"Event: {request.country} - {request.event_type}")
        
        # Mark simulation as running
        active_simulations[simulation_id] = {
            'status': 'running',
            'started_at': datetime.now().isoformat()
        }
        
        # Build event data for mapping
        event_data = {
            'country': request.country,
            'location': request.event_description,
            'event_type': request.event_type,
            'fatalities': request.fatalities,
            'event_date': request.date or datetime.now().strftime('%Y-%m-%d'),
            'notes': request.event_description,
            'latitude': request.lat,
            'longitude': request.lon,
            'event_id_cnty': request.event_id or f"evt_{simulation_id}"
        }
        
        # Map event to ticker
        if request.affected_tickers and len(request.affected_tickers) > 0:
            ticker = request.affected_tickers[0]
            logger.info(f"Using provided ticker: {ticker}")
        else:
            ticker = map_event_to_ticker(event_data)
            if not ticker:
                raise HTTPException(
                    status_code=400,
                    detail="Unable to map event to ASX ticker. Please specify affected_tickers."
                )
            logger.info(f"Mapped event to ticker: {ticker}")
        
        ticker_info = get_ticker_info(ticker)
        if not ticker_info:
            raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
        
        # Run simulation (this is the Phase 1 simulation engine)
        start_time = datetime.now()
        
        # Import simulation components
        from scripts.test_core import Simulation
        from llm_router import LLMRouter
        
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
