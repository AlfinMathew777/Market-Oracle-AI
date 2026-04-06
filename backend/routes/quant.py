"""Quant Engine API router — three new endpoints for quantitative analysis.

ADDITIVE ONLY — does not modify or overlap with any existing endpoints.

New endpoints:
  GET /api/quant/analyse/{ticker}     — full quant analysis
  GET /api/quant/prediction/{ticker}  — lightweight direction + confidence
  GET /api/quant/monte-carlo/{ticker} — Monte Carlo simulation data

NOTE on URL convention: existing routes use /api/<resource>/... (no /v1/).
These endpoints match that convention for consistency with the codebase.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

router = APIRouter()
_limiter = Limiter(key_func=get_remote_address)

_MAX_TICKER_LEN = 12


def _validate_ticker(raw: str) -> str:
    """Normalise ticker to uppercase with .AX suffix. Raises 400 on bad input."""
    t = raw.strip().upper()
    if not t:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty")
    if len(t) > _MAX_TICKER_LEN:
        raise HTTPException(status_code=400, detail=f"Ticker too long (max {_MAX_TICKER_LEN} chars)")
    # Tolerate callers that omit the .AX suffix
    if not t.endswith(".AX"):
        t = f"{t}.AX"
    return t


# ── /api/quant/analyse/{ticker} ────────────────────────────────────────────

@router.get("/api/quant/analyse/{ticker}")
@_limiter.limit("10/minute")
async def quant_analyse(ticker: str, request: Request):
    """Full quantitative analysis: vol model, factor exposures, MC paths, risk metrics.

    Rate-limited to 10/min because it makes a live yfinance call and runs
    5 000 MC simulations (~200 ms). Use /api/quant/prediction for lightweight calls.
    """
    validated = _validate_ticker(ticker)
    try:
        from quant_engine import QuantEngine

        engine = QuantEngine(ticker=validated, horizon_days=30, n_simulations=5000)
        result = engine.analyse()
        if result.get("status") == "error":
            return {"status": "error", "detail": result.get("error", "Analysis failed")}
        return {"status": "success", "data": result}

    except ImportError:
        logger.error("QuantEngine unavailable — quant_engine package not importable")
        raise HTTPException(status_code=503, detail="Quant engine unavailable")
    except Exception as e:
        logger.error("quant_analyse error for %s: %s", validated, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal analysis error")


# ── /api/quant/prediction/{ticker} ─────────────────────────────────────────

@router.get("/api/quant/prediction/{ticker}")
@_limiter.limit("20/minute")
async def quant_prediction(ticker: str, request: Request):
    """Lightweight quant prediction — direction + confidence only.

    Runs 2 000 simulations instead of 5 000 for faster response.
    Suitable for embedding in the agent simulation result without slowing it down.
    """
    validated = _validate_ticker(ticker)
    try:
        from quant_engine import QuantEngine

        engine = QuantEngine(ticker=validated, horizon_days=30, n_simulations=2000)
        result = engine.prediction()
        if result.get("status") == "error":
            return {"status": "error", "detail": result.get("error", "Prediction failed")}
        return {"status": "success", "data": result}

    except ImportError:
        logger.error("QuantEngine unavailable — quant_engine package not importable")
        raise HTTPException(status_code=503, detail="Quant engine unavailable")
    except Exception as e:
        logger.error("quant_prediction error for %s: %s", validated, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal prediction error")


# ── /api/quant/monte-carlo/{ticker} ────────────────────────────────────────

@router.get("/api/quant/monte-carlo/{ticker}")
@_limiter.limit("10/minute")
async def quant_monte_carlo(
    ticker: str,
    request: Request,
    horizon_days: int = Query(default=30, ge=5, le=90, description="Simulation horizon in trading days"),
    n_simulations: int = Query(default=5000, ge=1000, le=10000, description="Number of GBM paths"),
):
    """Monte Carlo simulation data for the MonteCarloEngine frontend visualisation.

    Returns percentile price paths and tail probability estimates in the format
    consumed by the MonteCarloEngine.jsx React component.

    Response shape:
        {
            "ticker": "BHP.AX",
            "current_price": 50.22,
            "annual_drift": 0.06,
            "annual_vol": 0.28,
            "implied_vol": 0.29,
            "horizon_days": 30,
            "percentile_paths": {"p5": [...], "p25": [...], "mean": [...],
                                  "p75": [...], "p95": [...]},
            "probabilities": {"up": 0.55, "down_5pct": 0.12, ...},
            "var_95": 0.045,
            "cvar_95": 0.062,
            "signal_stability": 0.72,
            "vol_regime": "HIGH",
            "factor_exposures": [...],
            "generated_at": "2026-03-27T12:00:00Z"
        }
    """
    validated = _validate_ticker(ticker)
    try:
        from quant_engine import QuantEngine

        engine = QuantEngine(
            ticker=validated,
            horizon_days=horizon_days,
            n_simulations=n_simulations,
        )
        result = engine.analyse()
        if result.get("status") == "error":
            return {"status": "error", "detail": result.get("error", "Simulation failed")}

        # Shape response to match the spec and MonteCarloEngine.jsx expectations
        mc_data = {
            "ticker": result["ticker"],
            "current_price": result["current_price"],
            "annual_drift": result["annual_drift"],
            "annual_vol": result["annual_vol"],
            "implied_vol": result["implied_vol"],
            "horizon_days": result["horizon_days"],
            "percentile_paths": result["percentile_paths"],
            "probabilities": result["probabilities"],
            "var_95": result["var_95"],
            "cvar_95": result["cvar_95"],
            "signal_stability": result["signal_stability"],
            "vol_regime": result["vol_regime"],
            "factor_exposures": result["factor_exposures"],
            "generated_at": result["generated_at"],
        }
        return {"status": "success", "data": mc_data}

    except ImportError:
        logger.error("QuantEngine unavailable — quant_engine package not importable")
        raise HTTPException(status_code=503, detail="Quant engine unavailable")
    except Exception as e:
        logger.error("quant_monte_carlo error for %s: %s", validated, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal simulation error")
