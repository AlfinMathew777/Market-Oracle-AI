"""Quant Engine — quantitative analysis package for Market Oracle AI.

This package is ADDITIVE ONLY. It does not modify any existing modules,
routes, services, or the agent simulation pipeline.

Modules:
    engine.py           — QuantEngine orchestrator (main entry point)
    factor_model.py     — Market beta + momentum factor exposures
    volatility_model.py — Historical vol, EWMA, and regime classification
    monte_carlo.py      — GBM price-path simulation (distinct from
                          services/game_theory/monte_carlo.py which does
                          agent-vote confidence simulation)
    technical_analysis.py — RSI, MACD, Bollinger Bands, composite score
    risk_metrics.py     — VaR, CVaR, Sharpe ratio, max drawdown
"""

from .engine import QuantEngine

__all__ = ["QuantEngine"]
