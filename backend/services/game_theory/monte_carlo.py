"""
Monte Carlo Simulation Engine — Market Oracle AI
==================================================
Adds probabilistic range estimates to predictions.
Uses numpy for fast vectorised simulation.

All simulations run in < 100ms (acceptable latency).
seed=42 for reproducibility — same inputs produce same output.
"""

import logging
import os

import numpy as np
from dataclasses import dataclass
from typing import Optional

# Env-configurable simulation counts.
# 2,500 price sims: 95% CI width ~±1.96% vs ±0.98% for 10,000 — acceptable for 7-day swing trading.
# 500 confidence sims: sufficient for stability classification (stable/unstable).
_MC_PRICE_SIMS      = int(os.getenv("MC_SIMULATIONS", "2500"))
_MC_CONFIDENCE_SIMS = int(os.getenv("MC_CONFIDENCE_SIMS", "500"))

logger = logging.getLogger(__name__)


@dataclass
class MonteCarloConfidence:
    mean_confidence: float
    confidence_std: float
    direction_stability_pct: float   # bearish_wins % (raw MC metric)
    dominant_stability_pct: float    # dominant direction win rate (display metric)
    is_stable: bool
    dominant_direction: str
    conviction_label: str  # "HIGH" / "MEDIUM" / "LOW"


@dataclass
class MonteCarloPriceRange:
    current_price: float
    expected_price_7d: float
    expected_change_pct: float
    range_90pct_low: float
    range_90pct_high: float
    range_68pct_low: float
    range_68pct_high: float
    prob_down_5pct: float
    prob_up_5pct: float
    prob_down_10pct: float
    prob_up_10pct: float
    # CVaR risk metrics (defaults keep existing callers backward-compatible)
    var_95: float = 0.0
    cvar_95: float = 0.0
    var_99: float = 0.0
    cvar_99: float = 0.0
    expected_return: float = 0.0
    prob_profit: float = 0.0
    risk_adjusted_score: float = 0.0
    tail_risk_ratio: float = 1.0
    risk_level: str = "MEDIUM"
    var_interpretation: str = ""
    cvar_interpretation: str = ""


@dataclass
class MonteCarloChokepointImpact:
    expected_duration_days: float
    expected_exports_aud: int
    worst_case_exports_aud: int
    best_case_exports_aud: int
    prob_exceeds_1b_pct: float
    prob_exceeds_5b_pct: float
    prob_exceeds_10b_pct: float
    scenario_label: str


def run_confidence_monte_carlo(
    bullish: int,
    bearish: int,
    neutral: int,
    iron_ore_price: Optional[float] = None,
    iron_ore_uncertainty_pct: float = 3.0,
    n_simulations: int = _MC_CONFIDENCE_SIMS,
) -> MonteCarloConfidence:
    """
    Tests confidence score stability across 1,000 scenarios.
    Reveals whether the signal is robust or fragile.

    Varies iron ore price by its uncertainty and sees how many
    agent votes might flip — then checks if direction stays consistent.
    """
    try:
        rng = np.random.default_rng(seed=42)
        total = bullish + bearish + neutral

        if total == 0:
            return MonteCarloConfidence(
                mean_confidence=0,
                confidence_std=0,
                direction_stability_pct=50,
                dominant_stability_pct=50,
                is_stable=False,
                dominant_direction="neutral",
                conviction_label="LOW",
            )

        confidences = []
        bearish_wins = 0

        # Pre-draw all simulations at once (vectorised — faster)
        # Bootstrap resample the agent votes to model sampling uncertainty.
        # Each neutral agent has 50/50 chance of going either way on new info.
        p_bear = bearish / total
        p_bull = bullish / total
        p_neut = neutral / total

        # Resample all agents across all simulations at once
        resampled = rng.multinomial(total, [p_bear, p_bull, p_neut], size=n_simulations)
        sim_bearish_all = resampled[:, 0].astype(float)
        sim_bullish_all = resampled[:, 1].astype(float)
        sim_neutral_all = resampled[:, 2].astype(float)

        # Iron ore price shock — vectorised
        if iron_ore_price:
            price_shocks = rng.normal(0, iron_ore_uncertainty_pct / 100, n_simulations)
            shift_bear = (price_shocks < -0.03).astype(float) * rng.integers(0, 3, n_simulations)
            shift_bull = (price_shocks >  0.03).astype(float) * rng.integers(0, 3, n_simulations)
            sim_bearish_all += shift_bear
            sim_bullish_all += shift_bull

        for i in range(n_simulations):
            sim_bearish = sim_bearish_all[i]
            sim_bullish = sim_bullish_all[i]
            sim_neutral_val = sim_neutral_all[i]

            sim_total = sim_bullish + sim_bearish + sim_neutral_val
            if sim_total == 0:
                continue
            neutral_ratio = sim_neutral_val / sim_total
            base = abs(sim_bearish - sim_bullish) / sim_total
            conf = base * (1 - neutral_ratio)

            # Cap at 60% if neutral > 40%
            if neutral_ratio > 0.4:
                conf = min(conf, 0.6)

            confidences.append(conf * 100)
            if sim_bearish > sim_bullish:
                bearish_wins += 1

        confidences_arr = np.array(confidences)
        direction_stability = bearish_wins / n_simulations * 100
        dominant = "bearish" if direction_stability > 50 else "bullish"

        std  = float(np.std(confidences_arr))
        mean = float(np.mean(confidences_arr))

        # Conviction and stability based on direction consistency, not raw std.
        # Bootstrap resampling naturally creates high confidence std for skewed
        # vote distributions even when the signal is genuinely strong — so
        # direction_stability is the more reliable stability signal.
        #
        # IMPORTANT: direction_stability = bearish_wins / n_simulations * 100.
        # A stable BULLISH signal has bearish_wins near 0% (dominant direction wins ~100%).
        # A stable BEARISH signal has bearish_wins near 100%.
        # A stable signal means the dominant direction wins consistently (>70%).
        # Bug fix: previously only checked >70% which always failed for bullish signals.
        if dominant == "bearish":
            is_stable = direction_stability > 70
        else:
            is_stable = direction_stability < 30  # bullish wins >70% of the time

        if dominant == "bearish":
            conviction = "HIGH" if direction_stability > 75 else ("MEDIUM" if direction_stability > 65 else "LOW")
        else:
            conviction = "HIGH" if direction_stability < 25 else ("MEDIUM" if direction_stability < 35 else "LOW")

        # dominant_stability_pct = how often the dominant direction won.
        # For bullish: dominant wins = 100 - bearish_wins_pct
        # For bearish: dominant wins = bearish_wins_pct
        dominant_stability = (
            round(100 - direction_stability, 1) if dominant == "bullish"
            else round(direction_stability, 1)
        )

        return MonteCarloConfidence(
            mean_confidence=round(mean, 1),
            confidence_std=round(std, 1),
            direction_stability_pct=round(direction_stability, 1),
            dominant_stability_pct=dominant_stability,
            is_stable=is_stable,
            dominant_direction=dominant,
            conviction_label=conviction,
        )

    except Exception as e:
        logger.error("[MC CONFIDENCE] Error: %s", e)
        return MonteCarloConfidence(
            mean_confidence=0,
            confidence_std=0,
            direction_stability_pct=50,
            dominant_stability_pct=50,
            is_stable=False,
            dominant_direction="neutral",
            conviction_label="LOW",
        )


def run_price_range_monte_carlo(
    current_price: float,
    direction_probability: float,
    ticker: str = "BHP.AX",
    days: int = 7,
    n_simulations: int = _MC_PRICE_SIMS,
    price_series=None,
) -> MonteCarloPriceRange:
    """
    Simulates 10,000 possible price paths over next N days.
    Returns probability-weighted price range.

    direction_probability: 0–1 where >0.5 means bearish call.
    price_series: optional pandas Series of daily closes for volatility calibration.
                  When provided, EWMA-blended volatility replaces the hardcoded table.
    """
    try:
        rng = np.random.default_rng(seed=42)

        # Calibrate volatility from recent price history when available;
        # fall back to the hardcoded per-ticker table otherwise.
        timeframe = f"{days}_day"
        if price_series is not None and len(price_series) >= 22:
            from services.game_theory.volatility_calibration import calibrate_daily_vol
            vol, regime = calibrate_daily_vol(price_series, timeframe=timeframe)
            logger.info("[MC PRICE] %s calibrated vol=%.5f regime=%s", ticker, vol, regime)
        else:
            from services.game_theory.volatility_calibration import fallback_daily_vol
            vol = fallback_daily_vol(ticker)
            logger.info("[MC PRICE] %s using fallback vol=%.5f", ticker, vol)

        # Directional bias: direction_probability > 0.5 = bearish = negative drift.
        # Coefficient chosen so prob_down_5pct > 50% at direction_prob ≈ 0.69.
        bearish_strength = (direction_probability - 0.5) * 2
        daily_bias = -bearish_strength * 0.020  # at dp=0.69: ~-0.76%/day → -5.2% in 7d

        # Simulate price paths — shape: (n_simulations, days)
        daily_returns = rng.normal(daily_bias, vol, size=(n_simulations, days))
        cumulative_returns = np.cumprod(1 + daily_returns, axis=1)
        final_prices = current_price * cumulative_returns[:, -1]

        # Fractional returns for CVaR (reuse the same simulation paths)
        frac_returns = cumulative_returns[:, -1] - 1

        # ── CVaR risk metrics ─────────────────────────────────────────────
        from services.game_theory.cvar_optimizer import CVaROptimizer
        cvar_opt = CVaROptimizer()
        var_95 = round(cvar_opt.calculate_var(frac_returns, 0.95), 2)
        cvar_95 = round(cvar_opt.calculate_cvar(frac_returns, 0.95), 2)
        var_99 = round(cvar_opt.calculate_var(frac_returns, 0.99), 2)
        cvar_99 = round(cvar_opt.calculate_cvar(frac_returns, 0.99), 2)

        expected_return = round(float(np.mean(frac_returns)) * 100, 2)
        prob_profit = round(float(np.mean(frac_returns > 0)) * 100, 1)

        risk_adjusted_score = round(
            expected_return / abs(cvar_95) if abs(cvar_95) > 0.01 else 0.0, 3
        )
        tail_risk_ratio = round(
            abs(cvar_95) / abs(var_95) if abs(var_95) > 0.01 else 1.0, 2
        )

        cvar_abs = abs(cvar_95)
        if cvar_abs < 3:
            risk_level = "LOW"
        elif cvar_abs < 7:
            risk_level = "MEDIUM"
        elif cvar_abs < 12:
            risk_level = "HIGH"
        else:
            risk_level = "VERY HIGH"

        return MonteCarloPriceRange(
            current_price=round(current_price, 2),
            expected_price_7d=round(float(np.mean(final_prices)), 2),
            expected_change_pct=round(
                (float(np.mean(final_prices)) - current_price) / current_price * 100, 2
            ),
            range_90pct_low=round(float(np.percentile(final_prices, 5)), 2),
            range_90pct_high=round(float(np.percentile(final_prices, 95)), 2),
            range_68pct_low=round(float(np.percentile(final_prices, 16)), 2),
            range_68pct_high=round(float(np.percentile(final_prices, 84)), 2),
            prob_down_5pct=round(
                float(np.mean(final_prices < current_price * 0.95)) * 100, 1
            ),
            prob_up_5pct=round(
                float(np.mean(final_prices > current_price * 1.05)) * 100, 1
            ),
            prob_down_10pct=round(
                float(np.mean(final_prices < current_price * 0.90)) * 100, 1
            ),
            prob_up_10pct=round(
                float(np.mean(final_prices > current_price * 1.10)) * 100, 1
            ),
            var_95=var_95,
            cvar_95=cvar_95,
            var_99=var_99,
            cvar_99=cvar_99,
            expected_return=expected_return,
            prob_profit=prob_profit,
            risk_adjusted_score=risk_adjusted_score,
            tail_risk_ratio=tail_risk_ratio,
            risk_level=risk_level,
            var_interpretation=f"95% confident loss won't exceed {abs(var_95):.1f}%",
            cvar_interpretation=f"In worst 5% of scenarios, avg loss is {abs(cvar_95):.1f}%",
        )

    except Exception as e:
        logger.error("[MC PRICE] Error: %s", e)
        return MonteCarloPriceRange(
            current_price=current_price,
            expected_price_7d=current_price,
            expected_change_pct=0,
            range_90pct_low=round(current_price * 0.9, 2),
            range_90pct_high=round(current_price * 1.1, 2),
            range_68pct_low=round(current_price * 0.95, 2),
            range_68pct_high=round(current_price * 1.05, 2),
            prob_down_5pct=50,
            prob_up_5pct=50,
            prob_down_10pct=20,
            prob_up_10pct=20,
        )


def run_chokepoint_monte_carlo(
    chokepoint_id: str,
    base_exports_at_risk: float,
    n_simulations: int = _MC_PRICE_SIMS,
) -> MonteCarloChokepointImpact:
    """
    Simulates range of outcomes from a chokepoint disruption.
    Accounts for uncertainty in duration, severity, and market reaction.
    """
    try:
        rng = np.random.default_rng(seed=42)

        DURATION_PARAMS = {
            "strait_of_malacca": {"mean": 7,  "std": 5,  "min": 1, "max": 30},
            "strait_of_hormuz":  {"mean": 14, "std": 7,  "min": 3, "max": 60},
            "bab_el_mandeb":     {"mean": 21, "std": 14, "min": 7, "max": 90},
            "suez_canal":        {"mean": 10, "std": 6,  "min": 2, "max": 45},
            "cape_of_good_hope": {"mean": 5,  "std": 3,  "min": 1, "max": 14},
        }
        params = DURATION_PARAMS.get(
            chokepoint_id, {"mean": 7, "std": 5, "min": 1, "max": 30}
        )

        durations = np.clip(
            rng.normal(params["mean"], params["std"], n_simulations),
            params["min"], params["max"],
        )
        severities       = rng.uniform(0.3, 1.5, n_simulations)
        market_reactions = np.clip(rng.normal(1.0, 0.3, n_simulations), 0.1, 2.5)

        impacts = base_exports_at_risk * (durations / 7) * severities * market_reactions

        mean_impact = float(np.mean(impacts))
        if mean_impact > 5_000_000_000:
            label = "CRITICAL — Major disruption to Australian exports"
        elif mean_impact > 2_000_000_000:
            label = "SEVERE — Significant export disruption expected"
        elif mean_impact > 500_000_000:
            label = "MODERATE — Meaningful but manageable impact"
        else:
            label = "LOW — Limited direct impact on Australian exports"

        return MonteCarloChokepointImpact(
            expected_duration_days=round(float(np.mean(durations)), 1),
            expected_exports_aud=round(mean_impact),
            worst_case_exports_aud=round(float(np.percentile(impacts, 95))),
            best_case_exports_aud=round(float(np.percentile(impacts, 5))),
            prob_exceeds_1b_pct=round(
                float(np.mean(impacts > 1_000_000_000)) * 100, 1
            ),
            prob_exceeds_5b_pct=round(
                float(np.mean(impacts > 5_000_000_000)) * 100, 1
            ),
            prob_exceeds_10b_pct=round(
                float(np.mean(impacts > 10_000_000_000)) * 100, 1
            ),
            scenario_label=label,
        )

    except Exception as e:
        logger.error("[MC CHOKEPOINT] Error: %s", e)
        return MonteCarloChokepointImpact(
            expected_duration_days=7,
            expected_exports_aud=int(base_exports_at_risk),
            worst_case_exports_aud=int(base_exports_at_risk * 3),
            best_case_exports_aud=int(base_exports_at_risk * 0.3),
            prob_exceeds_1b_pct=50,
            prob_exceeds_5b_pct=20,
            prob_exceeds_10b_pct=5,
            scenario_label="Scenario data unavailable",
        )
