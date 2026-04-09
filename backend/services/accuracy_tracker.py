"""
Accuracy Tracking Service
-------------------------
Stores Reasoning Synthesizer predictions and resolves outcomes
against actual price movements.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Any

import yfinance as yf

from database import (
    save_reasoning_prediction,
    update_reasoning_outcome,
    get_reasoning_accuracy_stats,
    get_pending_reasoning_predictions,
)
from models.reasoning_output import ReasoningOutput
from models.trade_execution import TradeExecution

logger = logging.getLogger(__name__)


async def store_prediction(
    reasoning_output: ReasoningOutput,
    current_price: float,
    trade_execution: Optional[TradeExecution] = None,
) -> str:
    """
    Persist a completed Reasoning Synthesizer prediction for outcome tracking.

    Generates a unique prediction_id, saves to DB, and returns the ID.
    Call this after every successful /api/reasoning/synthesize call.
    """
    prediction_id = str(uuid.uuid4())
    te = trade_execution

    await save_reasoning_prediction(
        prediction_id=prediction_id,
        stock_ticker=reasoning_output.stock_ticker,
        direction=reasoning_output.final_decision.direction.value,
        recommendation=reasoning_output.final_decision.recommendation.value,
        confidence_score=reasoning_output.final_decision.confidence_score,
        price_at_prediction=current_price,
        reasoning_output=reasoning_output.model_dump(exclude={"memory_context"}),
        trade_execution=te.model_dump() if te else None,
        entry_price=te.entry_price if te else None,
        stop_loss=te.stop_loss if te else None,
        take_profit_1=te.take_profit_1 if te else None,
        take_profit_2=te.take_profit_2 if te else None,
        take_profit_3=te.take_profit_3 if te else None,
        event_classification=reasoning_output.event_classification.model_dump(),
        causal_chain=reasoning_output.causal_chain.model_dump(),
        market_context=reasoning_output.market_context.model_dump(),
        agent_consensus=reasoning_output.consensus_analysis.model_dump(),
    )
    return prediction_id


async def resolve_pending_predictions() -> int:
    """
    Scheduled job: check PENDING predictions and update their outcomes.
    Uses yfinance to fetch current prices. Returns number of predictions resolved.
    """
    pending = await get_pending_reasoning_predictions()
    if not pending:
        return 0

    resolved_count = 0
    for pred in pending:
        try:
            current_price = _fetch_price(pred["stock_ticker"])
            if current_price is None:
                continue

            outcome = _evaluate_outcome(
                direction=pred["direction"],
                entry_price=pred["price_at_prediction"],
                current_price=current_price,
                stop_loss=pred.get("stop_loss"),
                tp1=pred.get("take_profit_1"),
                tp2=pred.get("take_profit_2"),
                tp3=pred.get("take_profit_3"),
                prediction_age_days=_age_days(pred["prediction_timestamp"]),
            )

            if outcome["status"] == "PENDING":
                continue  # Still too early to call

            await update_reasoning_outcome(
                prediction_id=pred["id"],
                outcome_status=outcome["status"],
                actual_return_pct=outcome["return_pct"],
                hit_tp1=outcome["hit_tp1"],
                hit_tp2=outcome["hit_tp2"],
                hit_tp3=outcome["hit_tp3"],
                hit_stop_loss=outcome["hit_stop"],
            )
            resolved_count += 1

        except Exception as e:
            logger.error("Error resolving prediction %s: %s", pred.get("id"), e)

    logger.info("Resolved %d/%d pending reasoning predictions", resolved_count, len(pending))
    return resolved_count


def _fetch_price(ticker: str) -> Optional[float]:
    """Fetch current price via yfinance."""
    try:
        info = yf.Ticker(ticker).fast_info
        return getattr(info, "last_price", None)
    except Exception as e:
        logger.warning("Price fetch failed for %s: %s", ticker, e)
        return None


def _age_days(prediction_timestamp: str) -> int:
    """Calculate how many days old a prediction is."""
    try:
        ts = datetime.fromisoformat(prediction_timestamp.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).days
    except Exception:
        return 0


def _evaluate_outcome(
    direction: str,
    entry_price: float,
    current_price: float,
    stop_loss: Optional[float],
    tp1: Optional[float],
    tp2: Optional[float],
    tp3: Optional[float],
    prediction_age_days: int,
) -> dict[str, Any]:
    """Determine the outcome of a prediction based on current price."""

    return_pct = ((current_price - entry_price) / entry_price) * 100

    if direction.upper() == "BULLISH":
        direction_correct = current_price > entry_price
        hit_stop = bool(stop_loss and current_price <= stop_loss)
        hit_tp1 = bool(tp1 and current_price >= tp1)
        hit_tp2 = bool(tp2 and current_price >= tp2)
        hit_tp3 = bool(tp3 and current_price >= tp3)
    else:  # Bearish
        direction_correct = current_price < entry_price
        return_pct = -return_pct
        hit_stop = bool(stop_loss and current_price >= stop_loss)
        hit_tp1 = bool(tp1 and current_price <= tp1)
        hit_tp2 = bool(tp2 and current_price <= tp2)
        hit_tp3 = bool(tp3 and current_price <= tp3)

    if hit_stop:
        status = "STOPPED_OUT"
    elif hit_tp3 or (hit_tp1 and direction_correct):
        status = "CORRECT"
    elif hit_tp1:
        status = "PARTIAL"
    elif prediction_age_days >= 30:
        status = "EXPIRED"
    elif direction_correct and return_pct >= 2:
        status = "CORRECT"
    elif not direction_correct and return_pct <= -2:
        status = "INCORRECT"
    else:
        status = "PENDING"

    return {
        "status": status,
        "return_pct": round(return_pct, 4),
        "hit_tp1": hit_tp1,
        "hit_tp2": hit_tp2,
        "hit_tp3": hit_tp3,
        "hit_stop": hit_stop,
    }


async def get_accuracy_summary(
    ticker: Optional[str] = None,
    direction: Optional[str] = None,
    days: int = 90,
) -> dict[str, Any]:
    """Public accessor for accuracy metrics — called by the API route."""
    return await get_reasoning_accuracy_stats(ticker=ticker, direction=direction, days=days)


async def get_resolved_predictions_for_eval(
    ticker: Optional[str] = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    """
    Fetch resolved predictions in the format needed by PredictionEvaluator and
    FailureAnalyzer.

    Derives `actual_direction` and `was_correct` from `direction` + `outcome_status`
    without requiring a schema change:
    - CORRECT / PARTIAL → actual matches predicted
    - INCORRECT / STOPPED_OUT → actual is opposite of predicted
    """
    from database import get_db, init_db
    from datetime import timedelta

    try:
        await init_db()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        conditions = ["prediction_timestamp >= ?", "outcome_status NOT IN ('PENDING', 'EXPIRED')"]
        params: list = [since]
        if ticker:
            conditions.append("stock_ticker = ?")
            params.append(ticker)

        where = " AND ".join(conditions)
        async with get_db() as db:
            db.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            async with db.execute(
                f"""SELECT id, stock_ticker as ticker, direction,
                           outcome_status, confidence_score as confidence,
                           actual_return_pct, agent_consensus, causal_chain
                    FROM reasoning_predictions
                    WHERE {where}
                    ORDER BY prediction_timestamp DESC
                    LIMIT 500""",
                params,
            ) as cur:
                rows = await cur.fetchall()

        _OPPOSITE = {"BULLISH": "BEARISH", "BEARISH": "BULLISH", "NEUTRAL": "NEUTRAL"}

        result = []
        for row in rows:
            predicted = row["direction"].upper()
            status = row["outcome_status"]
            was_correct = status in ("CORRECT", "PARTIAL")
            actual = (
                predicted if was_correct else _OPPOSITE.get(predicted, "NEUTRAL")
            )
            result.append({
                "id": row["id"],
                "ticker": row["ticker"],
                "predicted_direction": predicted,
                "actual_direction": actual,
                "was_correct": was_correct,
                "confidence": row["confidence"],
                "actual_return_pct": row["actual_return_pct"],
                "agent_votes": {},  # Not stored per-row; placeholder
                "causal_chain": {},
            })

        return result

    except Exception as exc:
        logger.error("get_resolved_predictions_for_eval failed: %s", exc)
        return []
