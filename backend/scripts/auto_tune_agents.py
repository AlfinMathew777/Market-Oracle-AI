"""
scripts/auto_tune_agents.py
================================================================================
Autonomous Configuration Optimizer — inspired by karpathy/autoresearch

Applies the "iterate with a clear metric" pattern to Market Oracle AI's
agent pipeline instead of ML training weights.

  autoresearch pattern:   modify train.py -> 5-min GPU run -> measure val_bpb -> keep if better
  Our pattern:            mutate config  -> replay history -> measure accuracy  -> keep if better

== PHASE 1  (zero LLM cost) ====================================================
  Mathematically optimises the vote->direction pipeline using stored predictions:
    • calculate_confidence()    — neutral-cap threshold & cap value
    • determine_direction()     — majority-margin & volume thresholds
    • apply_minimum_confidence_guard() — hard-zero & low-conf thresholds
    • Persona distribution bias — bear/bull balance per trend state

== PHASE 2  (low LLM cost) ======================================================
  LLM judge evaluates which prompt *rules* are misfiring on historical events
  and suggests softening/hardening specific rules.

Usage
-----
    python scripts/auto_tune_agents.py                  # Phase 1 only (default)
    python scripts/auto_tune_agents.py --phase 2        # Phase 1 + 2
    python scripts/auto_tune_agents.py --rounds 500     # More hill-climb steps
    python scripts/auto_tune_agents.py --apply          # Patch test_core.py constants

Output
------
    backend/prompt_configs/best_config.json    — best found config
    backend/prompt_configs/run_log.jsonl       — per-round results (append)

== ROADMAP ======================================================================

  MONTH 1-2 (now):
    Run Phase 1 on synthetic data to validate the optimizer loop.
    Collect real resolved predictions via run_reflection.py.
    Re-run once you have ~30 resolved rows with agent vote data.

  MONTH 2-3:
    Run Phase 2 (--phase 2) once you have enough misfires to analyse.
    Use --apply to patch test_core.py with the best found parameters.

  MONTH 3-4 (future enhancement — do not implement yet):
    Regime-aware tuning: instead of one global parameter set, tune a
    separate config per trend regime and select it at prediction time.

    def tune_by_regime(predictions: list) -> dict:
        '''
        Tunes separate parameter sets for each trend regime.

        Instead of one global parameter set:
          params_STRONG_DOWNTREND = tune(downtrend_predictions)
          params_SIDEWAYS         = tune(sideways_predictions)
          params_STRONG_UPTREND   = tune(uptrend_predictions)

        The system automatically selects the right params
        based on the current trend_label before each simulation.

        Prerequisite: enough predictions per regime (aim for 50+ per bucket).
        Use get_detailed_accuracy_stats() to check per-trend sample sizes first.
        '''

    Why this will matter: the optimal majority_margin for a STRONG_DOWNTREND
    is likely different from STRONG_UPTREND. Global tuning averages these out.
    Regime-aware tuning lets each regime use its own best thresholds.
    Expected gain: +5-15% accuracy once per-regime sample sizes are sufficient.
================================================================================
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import os
import random
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# -- Path setup ----------------------------------------------------------------
_SCRIPT_DIR  = Path(__file__).resolve().parent          # backend/scripts/
_BACKEND_DIR = _SCRIPT_DIR.parent                        # backend/
_PROJECT_DIR = _BACKEND_DIR.parent                       # repo root
_CONFIG_DIR  = _BACKEND_DIR / "prompt_configs"

sys.path.insert(0, str(_BACKEND_DIR))

# -- Logging -------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,          # suppress library noise
    format="%(levelname)s  %(message)s",
)
logger = logging.getLogger("auto_tune")
logger.setLevel(logging.INFO)

# -- DB path (mirrors database.py logic) --------------------------------------
_DB_DIR  = os.environ.get("DATA_DIR", "/data" if os.path.isdir("/data") else str(_BACKEND_DIR))
DB_PATH  = os.path.join(_DB_DIR, "aussieintel.db")


# ==============================================================================
# Config dataclass — every number here is a tunable parameter
# ==============================================================================

@dataclass
class AgentConfig:
    """
    All tunable numeric parameters of the vote->prediction pipeline.
    Baseline values mirror the current hardcoded constants in test_core.py.
    """

    # -- calculate_confidence() ------------------------------------------------
    neutral_cap_threshold: float = 0.40   # neutral ratio above which we cap
    neutral_cap_value:     float = 0.60   # cap value when threshold exceeded

    # -- determine_direction() -------------------------------------------------
    majority_margin:           int   = 5    # min vote gap for "clear" majority
    volume_dist_threshold:     float = 2.0  # volume_vs_avg ≥ this -> distribution
    volume_neutral_ratio:      float = 0.4  # neutral_ratio ≥ this on high-vol -> bearish
    low_vol_threshold:         float = 1.3  # volume_vs_avg < this = "low volume"

    # -- apply_minimum_confidence_guard() -------------------------------------
    hard_zero_threshold:         float = 3.0   # % below -> always neutral
    low_conf_threshold:          float = 15.0  # % below (+ chain override) -> warning
    near_tie_vote_margin:        int   = 2     # max vote gap for "near-tie" condition
    near_tie_conf_threshold:     float = 15.0  # % below which near-tie -> neutral

    # -- Persona distribution bias (applied on top of trend weights) -----------
    # Positive = add more bears vs bulls; Negative = add more bulls vs bears
    # These are *offsets* applied to the baseline distribution counts.
    #   e.g. bear_bias_downtrend = +2  means  geo_bear += 2, macro_bull -= 2
    bear_bias_strong_downtrend: int = 0
    bear_bias_downtrend:        int = 0
    bear_bias_neutral:          int = 0
    bear_bias_uptrend:          int = 0
    bear_bias_strong_uptrend:   int = 0

    # -- Metadata (not tuned) -------------------------------------------------
    description: str = "baseline"


BASELINE_CONFIG = AgentConfig()

# Allowed mutation ranges (min, max, step)
_FLOAT_PARAMS = {
    "neutral_cap_threshold":    (0.20, 0.65, 0.05),
    "neutral_cap_value":        (0.40, 0.85, 0.05),
    "volume_dist_threshold":    (1.5,  3.0,  0.25),
    "volume_neutral_ratio":     (0.25, 0.60, 0.05),
    "low_vol_threshold":        (1.0,  2.0,  0.1),
    "hard_zero_threshold":      (1.0,  8.0,  0.5),
    "low_conf_threshold":       (8.0,  25.0, 1.0),
    "near_tie_conf_threshold":  (8.0,  25.0, 1.0),
}
_INT_PARAMS = {
    "majority_margin":          (2, 10, 1),
    "near_tie_vote_margin":     (1, 5,  1),
    "bear_bias_strong_downtrend": (-3, 5, 1),
    "bear_bias_downtrend":      (-3, 5, 1),
    "bear_bias_neutral":        (-3, 3, 1),
    "bear_bias_uptrend":        (-5, 3, 1),
    "bear_bias_strong_uptrend": (-5, 3, 1),
}


# ==============================================================================
# Replay pipeline  (pure Python, zero LLM calls)
# ==============================================================================

def _calc_confidence(bull: int, bear: int, neut: int, cfg: AgentConfig) -> float:
    """Replay of calculate_confidence() with tunable parameters."""
    total = bull + bear + neut
    if total == 0:
        return 0.0
    base          = abs(bear - bull) / total
    neutral_ratio = neut / total
    confidence    = base * (1.0 - neutral_ratio)
    if neutral_ratio > cfg.neutral_cap_threshold:
        confidence = min(confidence, cfg.neutral_cap_value)
    return round(confidence, 3)


def _determine_dir(
    bull: int, bear: int, neut: int,
    volume_vs_avg: Optional[float],
    has_catalyst: bool,
    confidence: float,
    cfg: AgentConfig,
) -> str:
    """Replay of determine_direction() with tunable parameters."""
    total        = bull + bear + neut
    neut_ratio   = neut / total if total > 0 else 0
    no_catalyst  = not has_catalyst

    if bull > bear and (bull - bear) >= cfg.majority_margin:
        return "bullish"
    if bear > bull and (bear - bull) >= cfg.majority_margin:
        return "bearish"

    if (
        volume_vs_avg is not None
        and volume_vs_avg >= cfg.volume_dist_threshold
        and neut_ratio > cfg.volume_neutral_ratio
    ):
        return "bearish"

    if no_catalyst and (volume_vs_avg is None or volume_vs_avg < cfg.low_vol_threshold):
        return "neutral"

    if bull == bear:
        return "bearish"

    return "bullish" if bull > bear else "bearish"


def _min_conf_guard(
    direction: str,
    confidence_pct: float,
    bull: int, bear: int, neut: int,
    chain_override: bool,
    cfg: AgentConfig,
) -> str:
    """
    Replay of apply_minimum_confidence_guard(); returns only the final direction
    (we don't need the note string for scoring).
    """
    total      = bull + bear + neut
    neut_ratio = neut / total if total > 0 else 1.0

    if chain_override and direction != "neutral":
        return direction

    if confidence_pct < cfg.hard_zero_threshold:
        return "neutral"

    margin = abs(bull - bear)
    if margin <= cfg.near_tie_vote_margin and confidence_pct < cfg.near_tie_conf_threshold:
        return "neutral"

    return direction


def _apply_persona_bias(
    bull: int, bear: int, neut: int,
    trend_label: str,
    cfg: AgentConfig,
) -> Tuple[int, int, int]:
    """
    Apply bear/bull bias offset to stored vote counts.
    A positive bias_offset adds to bear, subtracts from bull (capped at 0).
    """
    bias_map = {
        "STRONG_DOWNTREND": cfg.bear_bias_strong_downtrend,
        "DOWNTREND":        cfg.bear_bias_downtrend,
        "NEUTRAL":          cfg.bear_bias_neutral,
        "SIDEWAYS":         cfg.bear_bias_neutral,
        "UPTREND":          cfg.bear_bias_uptrend,
        "STRONG_UPTREND":   cfg.bear_bias_strong_uptrend,
        "UNKNOWN":          cfg.bear_bias_neutral,
    }
    bias = bias_map.get(trend_label, 0)
    if bias == 0:
        return bull, bear, neut

    # Positive bias -> shift votes from bull to bear (or vice-versa for negative)
    shift = abs(bias)
    if bias > 0:
        transfer = min(shift, bull)
        return max(0, bull - transfer), bear + transfer, neut
    else:
        transfer = min(shift, bear)
        return bull + transfer, max(0, bear - transfer), neut


def replay_prediction(row: dict, cfg: AgentConfig) -> str:
    """
    Given a stored prediction row and a config, replay the pipeline and return
    the direction that *would* have been predicted.
    """
    bull   = row["agent_bullish"]  or 0
    bear   = row["agent_bearish"]  or 0
    neut   = row["agent_neutral"]  or 0
    trend  = row["trend_label"]    or "UNKNOWN"

    # Apply persona distribution bias
    bull, bear, neut = _apply_persona_bias(bull, bear, neut, trend, cfg)

    conf       = _calc_confidence(bull, bear, neut, cfg)
    conf_pct   = conf * 100.0

    # We don't have volume_vs_avg stored — treat as None (conservative)
    # We assume a catalyst exists if event is non-trivial
    has_catalyst = True   # prediction_log entries are always real events
    chain_override = False  # we can't know this without re-running causal audit

    direction = _determine_dir(bull, bear, neut, None, has_catalyst, conf_pct, cfg)
    direction = _min_conf_guard(direction, conf_pct, bull, bear, neut, chain_override, cfg)
    return direction


# ==============================================================================
# Data loading
# ==============================================================================

def load_resolved_predictions() -> List[dict]:
    """
    Load all resolved predictions from prediction_log where we know the outcome.
    Falls back to simulations table if prediction_log is empty.
    """
    if not os.path.exists(DB_PATH):
        logger.warning("Database not found at %s — running with synthetic data", DB_PATH)
        return _synthetic_predictions()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Try prediction_log first (Upgrade 5 schema)
        try:
            rows = conn.execute("""
                SELECT
                    agent_bullish,
                    agent_bearish,
                    agent_neutral,
                    trend_label,
                    actual_direction,
                    predicted_direction,
                    confidence,
                    prediction_correct
                FROM prediction_log
                WHERE prediction_correct IS NOT NULL
                  AND actual_direction IS NOT NULL
                  AND agent_bullish IS NOT NULL
                ORDER BY predicted_at DESC
            """).fetchall()
            rows = [dict(r) for r in rows]
            if rows:
                logger.info("Loaded %d resolved predictions from prediction_log", len(rows))
                return rows
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet

        # Fallback: simulations table
        rows = conn.execute("""
            SELECT
                agent_votes,
                outcome,
                direction AS predicted_direction,
                confidence
            FROM simulations
            WHERE outcome IN ('CORRECT', 'INCORRECT', 'NEUTRAL')
              AND agent_votes IS NOT NULL
            ORDER BY created_at DESC
        """).fetchall()

        def _normalise(d: str) -> str:
            """Normalise UP/DOWN/NEUTRAL -> bullish/bearish/neutral."""
            d = (d or "").strip().lower()
            return {"up": "bullish", "down": "bearish"}.get(d, d)

        results = []
        for r in rows:
            r = dict(r)
            try:
                votes = json.loads(r["agent_votes"]) if r["agent_votes"] else []
                bull  = sum(1 for v in votes if v.get("vote", "").lower() in ("bullish", "up"))
                bear  = sum(1 for v in votes if v.get("vote", "").lower() in ("bearish", "down"))
                neut  = sum(1 for v in votes if v.get("vote", "").lower() in ("neutral",))
            except Exception:
                continue
            outcome   = r["outcome"]
            pred_dir  = _normalise(r["predicted_direction"])
            actual = pred_dir if outcome == "CORRECT" else (
                "neutral" if outcome == "NEUTRAL" else
                ("bearish" if pred_dir == "bullish" else "bullish")
            )
            results.append({
                "agent_bullish":       bull,
                "agent_bearish":       bear,
                "agent_neutral":       neut,
                "trend_label":         "UNKNOWN",
                "actual_direction":    actual,
                "predicted_direction": pred_dir,
                "confidence":          r["confidence"],
                "prediction_correct":  1 if outcome == "CORRECT" else 0,
            })

        # Drop rows where all vote counts are zero (empty agent_votes arrays)
        results = [r for r in results if (r["agent_bullish"] + r["agent_bearish"] + r["agent_neutral"]) > 0]

        if results:
            logger.info("Loaded %d resolved predictions with vote data from simulations table", len(results))
        else:
            logger.warning(
                "No predictions with agent vote data found "
                "(agent_votes field is empty — run a few simulations first). "
                "Using synthetic benchmark dataset."
            )
            results = _synthetic_predictions()
        return results

    finally:
        conn.close()


def _synthetic_predictions() -> List[dict]:
    """
    Synthetic dataset for running the optimizer when DB has no history yet.
    Based on realistic edge cases that expose misconfiguration in the pipeline.
    """
    cases = [
        # Clear bearish signal
        {"agent_bullish": 5, "agent_bearish": 30, "agent_neutral": 10, "trend_label": "STRONG_DOWNTREND",
         "actual_direction": "bearish", "predicted_direction": "bearish", "confidence": 0.51, "prediction_correct": 1},
        # Clear bullish signal
        {"agent_bullish": 30, "agent_bearish": 5, "agent_neutral": 10, "trend_label": "STRONG_UPTREND",
         "actual_direction": "bullish", "predicted_direction": "bullish", "confidence": 0.55, "prediction_correct": 1},
        # Near-split — should be neutral or bearish
        {"agent_bullish": 18, "agent_bearish": 19, "agent_neutral": 8, "trend_label": "NEUTRAL",
         "actual_direction": "neutral", "predicted_direction": "bearish", "confidence": 0.02, "prediction_correct": 0},
        # High neutral — undecided market
        {"agent_bullish": 10, "agent_bearish": 12, "agent_neutral": 23, "trend_label": "NEUTRAL",
         "actual_direction": "neutral", "predicted_direction": "bearish", "confidence": 0.04, "prediction_correct": 0},
        # Downtrend reversal
        {"agent_bullish": 20, "agent_bearish": 15, "agent_neutral": 10, "trend_label": "DOWNTREND",
         "actual_direction": "bullish", "predicted_direction": "bullish", "confidence": 0.10, "prediction_correct": 1},
        # Uptrend continuation
        {"agent_bullish": 25, "agent_bearish": 8, "agent_neutral": 12, "trend_label": "UPTREND",
         "actual_direction": "bullish", "predicted_direction": "bullish", "confidence": 0.37, "prediction_correct": 1},
        # Bear trap
        {"agent_bullish": 10, "agent_bearish": 20, "agent_neutral": 15, "trend_label": "NEUTRAL",
         "actual_direction": "bullish", "predicted_direction": "bearish", "confidence": 0.22, "prediction_correct": 0},
        # Weak signal -> should go neutral
        {"agent_bullish": 16, "agent_bearish": 17, "agent_neutral": 12, "trend_label": "NEUTRAL",
         "actual_direction": "neutral", "predicted_direction": "bearish", "confidence": 0.02, "prediction_correct": 0},
        # Strong downtrend continuation
        {"agent_bullish": 3, "agent_bearish": 35, "agent_neutral": 7, "trend_label": "STRONG_DOWNTREND",
         "actual_direction": "bearish", "predicted_direction": "bearish", "confidence": 0.70, "prediction_correct": 1},
        # Uptrend with mixed signals
        {"agent_bullish": 22, "agent_bearish": 10, "agent_neutral": 13, "trend_label": "UPTREND",
         "actual_direction": "bullish", "predicted_direction": "bullish", "confidence": 0.28, "prediction_correct": 1},
        # Extreme neutral (market paralysis)
        {"agent_bullish": 8, "agent_bearish": 9, "agent_neutral": 28, "trend_label": "NEUTRAL",
         "actual_direction": "neutral", "predicted_direction": "bearish", "confidence": 0.02, "prediction_correct": 0},
        # Bearish with uptrend context
        {"agent_bullish": 8, "agent_bearish": 25, "agent_neutral": 12, "trend_label": "UPTREND",
         "actual_direction": "bearish", "predicted_direction": "bearish", "confidence": 0.38, "prediction_correct": 1},
        # Very high bull majority
        {"agent_bullish": 38, "agent_bearish": 2, "agent_neutral": 5, "trend_label": "STRONG_UPTREND",
         "actual_direction": "bullish", "predicted_direction": "bullish", "confidence": 0.78, "prediction_correct": 1},
        # Moderate bear with downtrend
        {"agent_bullish": 10, "agent_bearish": 22, "agent_neutral": 13, "trend_label": "DOWNTREND",
         "actual_direction": "bearish", "predicted_direction": "bearish", "confidence": 0.28, "prediction_correct": 1},
        # Confused market — high neutral in downtrend
        {"agent_bullish": 12, "agent_bearish": 14, "agent_neutral": 19, "trend_label": "DOWNTREND",
         "actual_direction": "neutral", "predicted_direction": "bearish", "confidence": 0.04, "prediction_correct": 0},
    ]
    logger.info("Using %d synthetic prediction cases", len(cases))
    return cases


# ==============================================================================
# Scoring
# ==============================================================================

def score_config(cfg: AgentConfig, predictions: List[dict]) -> float:
    """
    Replay each prediction with the given config and return accuracy (0.0–1.0).
    Only counts non-neutral actuals for direction accuracy; neutral actuals are
    checked for correct neutral prediction.
    """
    if not predictions:
        return 0.0

    correct = 0
    for row in predictions:
        predicted = replay_prediction(row, cfg)
        actual    = (row.get("actual_direction") or "").lower()
        correct  += int(predicted == actual)

    return correct / len(predictions)


# ==============================================================================
# Mutation
# ==============================================================================

def mutate_config(cfg: AgentConfig) -> Tuple[AgentConfig, str]:
    """
    Return (new_config, description_of_change).
    Mutates exactly ONE parameter by one step in a random direction.
    """
    new_cfg = copy.deepcopy(cfg)
    all_params = list(_FLOAT_PARAMS.keys()) + list(_INT_PARAMS.keys())
    param = random.choice(all_params)

    if param in _FLOAT_PARAMS:
        lo, hi, step = _FLOAT_PARAMS[param]
        current = getattr(new_cfg, param)
        delta   = random.choice([-step, +step])
        new_val = round(max(lo, min(hi, current + delta)), 4)
        setattr(new_cfg, param, new_val)
        desc = f"{param}: {current:.3f} -> {new_val:.3f}"
    else:
        lo, hi, step = _INT_PARAMS[param]
        current = getattr(new_cfg, param)
        delta   = random.choice([-step, +step])
        new_val = max(lo, min(hi, current + delta))
        setattr(new_cfg, param, new_val)
        desc = f"{param}: {current} -> {new_val}"

    new_cfg.description = desc
    return new_cfg, desc


# ==============================================================================
# Persistence
# ==============================================================================

def save_config(cfg: AgentConfig, name: str = "best_config.json") -> Path:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _CONFIG_DIR / name
    with open(path, "w") as f:
        json.dump(asdict(cfg), f, indent=2)
    return path


def load_config(name: str = "best_config.json") -> Optional[AgentConfig]:
    path = _CONFIG_DIR / name
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return AgentConfig(**{k: v for k, v in data.items() if k in AgentConfig.__dataclass_fields__})


def append_run_log(entry: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CONFIG_DIR / "run_log.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


# ==============================================================================
# Phase 1 — Hill-climbing optimizer
# ==============================================================================

def run_phase1(predictions: List[dict], rounds: int = 300) -> AgentConfig:
    """
    Hill-climbing loop (the autoresearch pattern):
    - Start from last best_config.json or baseline
    - Each round: mutate one param, score, keep if better
    - Log every round for transparency
    """
    baseline_acc = score_config(BASELINE_CONFIG, predictions)
    n = len(predictions)

    # Resume from prior best only if it's actually better than baseline on THIS dataset
    prior = load_config()
    if prior is not None:
        prior_acc = score_config(prior, predictions)
        if prior_acc >= baseline_acc:
            start_cfg = prior
            start_acc = prior_acc
        else:
            logger.info("Prior best_config is worse than baseline on current dataset — resetting to baseline")
            start_cfg = copy.deepcopy(BASELINE_CONFIG)
            start_acc = baseline_acc
    else:
        start_cfg = copy.deepcopy(BASELINE_CONFIG)
        start_acc = baseline_acc

    bar = "=" * 60

    print(f"\n{bar}")
    print(f"  PHASE 1 - Mathematical Optimizer")
    print(f"  Dataset:  {n} resolved predictions")
    print(f"  Rounds:   {rounds}")
    print(f"  Baseline accuracy: {baseline_acc*100:.1f}%")
    if start_acc > baseline_acc:
        print(f"  Resuming from prior best: {start_acc*100:.1f}%")
    print(f"{bar}\n")
    print(f"  {'Round':>6}  {'Accuracy':>9}  {'Delta':>7}  {'Action':6}  Change")
    print(f"  {'-'*6}  {'-'*9}  {'-'*7}  {'-'*6}  {'-'*35}")

    best_cfg = start_cfg
    best_acc = start_acc
    no_improve_streak = 0
    t0 = time.time()

    for i in range(1, rounds + 1):
        candidate, desc = mutate_config(best_cfg)
        acc = score_config(candidate, predictions)
        delta = acc - best_acc

        if acc >= best_acc:                      # accept equal-or-better (allows plateaus)
            action = "KEEP  "
            best_cfg = candidate
            best_acc = acc
            no_improve_streak = 0
        else:
            action = "revert"
            no_improve_streak += 1

        symbol = "^" if delta > 0 else ("v" if delta < 0 else "-")
        print(f"  {i:>6}  {acc*100:>8.2f}%  {symbol}{abs(delta)*100:>6.2f}%  {action}  {desc}")

        append_run_log({
            "phase": 1,
            "round": i,
            "accuracy": round(acc, 4),
            "delta": round(delta, 4),
            "accepted": acc >= best_acc,
            "change": desc,
            "timestamp": time.time(),
        })

        # Early stop: 80 rounds without improvement
        if no_improve_streak >= 80:
            print(f"\n  Early stop: {no_improve_streak} rounds without improvement")
            break

    elapsed = time.time() - t0
    improvement = best_acc - baseline_acc

    print(f"\n{bar}")
    print(f"  Phase 1 complete in {elapsed:.1f}s")
    print(f"  Final accuracy:  {best_acc*100:.1f}%")
    print(f"  vs baseline:    {'+' if improvement >= 0 else ''}{improvement*100:.1f}%")
    print(f"{bar}\n")

    return best_cfg


# ==============================================================================
# Phase 2 — LLM rule optimizer
# ==============================================================================

async def run_phase2(predictions: List[dict], best_cfg: AgentConfig) -> None:
    """
    Ask a judge LLM to review misfiring predictions and suggest rule changes.
    Produces a text report — does NOT auto-patch prompts (human-in-the-loop).
    """
    try:
        from llm_router import LLMRouter
    except ImportError:
        print("  !  Cannot import LLMRouter — skipping Phase 2")
        return

    # Find the predictions the baseline gets wrong
    wrong = []
    for row in predictions:
        replayed = replay_prediction(row, best_cfg)
        actual   = (row.get("actual_direction") or "").lower()
        if replayed != actual:
            wrong.append({
                "bull": row["agent_bullish"],
                "bear": row["agent_bearish"],
                "neut": row["agent_neutral"],
                "trend": row.get("trend_label", "UNKNOWN"),
                "predicted": replayed,
                "actual": actual,
                "stored_confidence": row.get("confidence", "?"),
            })

    if not wrong:
        print("  Phase 2: no misfires to analyse — skip")
        return

    print(f"\n  PHASE 2 — LLM Rule Analyser")
    print(f"  Analysing {len(wrong)} misfires with judge LLM …\n")

    misfire_text = "\n".join(
        f"  • {r['trend']} trend | votes {r['bull']}B/{r['bear']}Be/{r['neut']}N "
        f"-> predicted {r['predicted']} but actual was {r['actual']}"
        for r in wrong[:15]   # cap at 15 to stay within token budget
    )

    system = (
        "You are a senior quantitative analyst reviewing an AI prediction system. "
        "Your job is to identify *which pipeline rules* are causing misfires and "
        "suggest *specific, actionable* changes to fix them. "
        "Be concise. Output a JSON object."
    )
    user = f"""
The Market Oracle AI agent pipeline misfired on these predictions:

{misfire_text}

Current rules (abbreviated):
- TREND_MOMENTUM_RULE: Strong downtrend requires CRITICAL bullish evidence to vote bullish
- AUDUSD_RULE: AUD/USD drop > 0.5% = risk-off = BEARISH (override)
- BROAD_MARKET_RULE: Selloff requires CRITICAL bullish to justify bullish vote
- NEWS_PRIORITY_RULE: CRITICAL signals override all others
- RSI RULE: RSI < 25 = NEUTRAL unless CRITICAL bearish catalyst

Analyse the misfires and return JSON with this schema:
{{
  "root_cause_summary": "1-2 sentence diagnosis",
  "rule_adjustments": [
    {{
      "rule": "rule name",
      "current_behaviour": "what it does now",
      "suggested_change": "specific wording change",
      "expected_impact": "why this will reduce misfires"
    }}
  ],
  "distribution_recommendation": {{
    "observation": "what the vote patterns suggest",
    "suggestion": "any distribution bias to apply"
  }}
}}
"""

    try:
        router = LLMRouter()
        response = await router.call_primary(system, user, session_id="auto_tune_phase2")
        parsed   = router.parse_json_response(response)

        print("  -- Root Cause ------------------------------------------")
        print(f"  {parsed.get('root_cause_summary', 'N/A')}")
        print()

        adjustments = parsed.get("rule_adjustments", [])
        if adjustments:
            print("  -- Suggested Rule Changes ------------------------------")
            for adj in adjustments:
                print(f"  Rule:    {adj.get('rule')}")
                print(f"  Now:     {adj.get('current_behaviour')}")
                print(f"  Change:  {adj.get('suggested_change')}")
                print(f"  Impact:  {adj.get('expected_impact')}")
                print()

        dist = parsed.get("distribution_recommendation", {})
        if dist:
            print("  -- Distribution Recommendation -------------------------")
            print(f"  {dist.get('observation')}")
            print(f"  {dist.get('suggestion')}")
            print()

        # Save report
        report_path = _CONFIG_DIR / "phase2_report.json"
        with open(report_path, "w") as f:
            json.dump(parsed, f, indent=2)
        print(f"  Report saved -> {report_path}")

    except Exception as e:
        logger.error("Phase 2 LLM call failed: %s", e)
        print(f"  Phase 2 error: {e}")


# ==============================================================================
# --apply: patch test_core.py with best config
# ==============================================================================

def apply_config_to_test_core(cfg: AgentConfig) -> None:
    """
    Patch the numeric constants in test_core.py to match the best config.
    Only touches the specific lines that contain tuneable values.
    Creates a .bak backup before patching.
    """
    import re
    src = _BACKEND_DIR / "scripts" / "test_core.py"
    bak = src.with_suffix(".py.bak")

    text = src.read_text(encoding="utf-8")
    original = text

    # Backup
    bak.write_text(text, encoding="utf-8")
    print(f"  Backup -> {bak}")

    replacements = [
        # calculate_confidence: neutral_ratio > 0.40 -> configurable
        (r"if neutral_ratio > [0-9.]+:",
         f"if neutral_ratio > {cfg.neutral_cap_threshold}:"),
        (r"confidence = min\(confidence, [0-9.]+\)",
         f"confidence = min(confidence, {cfg.neutral_cap_value})"),
        # determine_direction: majority margin
        (r"\(bullish - bearish\) >= [0-9]+",
         f"(bullish - bearish) >= {cfg.majority_margin}"),
        (r"\(bearish - bullish\) >= [0-9]+",
         f"(bearish - bullish) >= {cfg.majority_margin}"),
        # volume thresholds
        (r"volume_vs_avg >= [0-9.]+ and neutral_ratio > [0-9.]+",
         f"volume_vs_avg >= {cfg.volume_dist_threshold} and neutral_ratio > {cfg.volume_neutral_ratio}"),
        (r"volume_vs_avg < [0-9.]+:",
         f"volume_vs_avg < {cfg.low_vol_threshold}:"),
        # hard zero threshold
        (r"if confidence < 3\.0:",
         f"if confidence < {cfg.hard_zero_threshold}:"),
        # low conf chain override
        (r"if confidence < 15\.0:",
         f"if confidence < {cfg.low_conf_threshold}:"),
        # near-tie margin
        (r"if margin <= [0-9]+ and confidence < [0-9.]+:",
         f"if margin <= {cfg.near_tie_vote_margin} and confidence < {cfg.near_tie_conf_threshold}:"),
    ]

    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    if text == original:
        print("  No changes needed — test_core.py already matches best config.")
        return

    src.write_text(text, encoding="utf-8")
    print(f"  ok Patched test_core.py with best config.")
    print(f"  To revert: cp {bak} {src}")


# ==============================================================================
# Main
# ==============================================================================

def _print_config_diff(baseline: AgentConfig, best: AgentConfig) -> None:
    b = asdict(baseline)
    t = asdict(best)
    changes = [(k, b[k], t[k]) for k in b if b[k] != t[k] and k != "description"]
    if not changes:
        print("  (no parameters changed from baseline)")
        return
    print(f"  {'Parameter':<35} {'Baseline':>12}  {'Best':>12}")
    print(f"  {'-'*35}  {'-'*12}  {'-'*12}")
    for k, bv, tv in changes:
        arrow = "^" if (isinstance(tv, (int, float)) and tv > bv) else "v"
        print(f"  {k:<35} {str(bv):>12}  {str(tv):>12}  {arrow}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-tune Market Oracle AI agent config")
    parser.add_argument("--phase",  type=int, default=1, choices=[1, 2],
                        help="1 = math only (default), 2 = math + LLM rule analysis")
    parser.add_argument("--rounds", type=int, default=300,
                        help="Hill-climbing rounds for Phase 1 (default: 300)")
    parser.add_argument("--apply",  action="store_true",
                        help="Patch test_core.py with best config after optimisation")
    parser.add_argument("--seed",   type=int, default=None,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    print("\n" + "=" * 60)
    print("  Market Oracle AI — Autonomous Config Optimizer")
    print("  (inspired by karpathy/autoresearch)")
    print("=" * 60)

    # Load data
    predictions = load_resolved_predictions()

    # Phase 1: mathematical hill-climbing
    best_cfg = run_phase1(predictions, rounds=args.rounds)

    # Save
    path = save_config(best_cfg)
    print(f"  Best config saved -> {path}\n")

    # Diff
    print("  -- Parameter changes vs baseline ------------------------")
    _print_config_diff(BASELINE_CONFIG, best_cfg)
    print()

    # Phase 2: LLM rule analysis (optional)
    if args.phase == 2:
        asyncio.run(run_phase2(predictions, best_cfg))

    # Apply to test_core.py
    if args.apply:
        print("\n  -- Applying config to test_core.py -------------------")
        apply_config_to_test_core(best_cfg)

    # Final summary
    baseline_acc = score_config(BASELINE_CONFIG, predictions)
    best_acc     = score_config(best_cfg, predictions)
    gain         = best_acc - baseline_acc
    n            = len(predictions)

    print(f"\n  -- Final Summary -----------------------------------------")
    print(f"  Predictions evaluated: {n}")
    print(f"  Baseline accuracy:     {baseline_acc*100:.1f}%  ({int(baseline_acc*n)}/{n})")
    print(f"  Best accuracy:         {best_acc*100:.1f}%  ({int(best_acc*n)}/{n})")
    print(f"  Net improvement:       {'+' if gain >= 0 else ''}{gain*100:.1f}%")
    print()

    if gain > 0.02:
        print("  Next step: run with --apply to patch test_core.py")
    elif gain <= 0:
        print("  Baseline is already optimal for this dataset.")
    else:
        print("  Marginal gain found — consider collecting more resolved predictions.")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
