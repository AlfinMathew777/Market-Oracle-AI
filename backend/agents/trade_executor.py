"""
Trade Execution Agent
---------------------
Converts prediction signals into actionable trade parameters.
Uses ATR-based position sizing and technical levels for entries/exits.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from models.trade_execution import (
    TradeExecution,
    TradeExecutionRequest,
    TradeAction,
    OrderType,
    TradeTimeframe,
    RiskRewardProfile,
    PriceLevel,
)

logger = logging.getLogger(__name__)


class TradeExecutor:
    """
    Generates trade execution plans from prediction signals.

    Key principles:
    - ATR-based stop-losses (volatility-adjusted)
    - Minimum 2:1 risk/reward ratio
    - Position sizing based on risk tolerance
    - Multiple take-profit levels for scaling out
    """

    RISK_MULTIPLIERS = {
        "conservative": {"atr_stop": 2.5, "position_pct": 1.0, "rr_min": 3.0},
        "moderate":     {"atr_stop": 2.0, "position_pct": 2.0, "rr_min": 2.0},
        "aggressive":   {"atr_stop": 1.5, "position_pct": 3.0, "rr_min": 1.5},
    }

    def generate_execution_plan(self, request: TradeExecutionRequest) -> Optional[TradeExecution]:
        """
        Generate a complete trade execution plan.

        Returns None for HOLD/WAIT recommendations or NEUTRAL direction.
        """
        if request.recommendation in ("HOLD", "WAIT", "AVOID"):
            logger.info("Skipping execution for %s: recommendation is %s",
                        request.stock_ticker, request.recommendation)
            return None

        if request.direction == "NEUTRAL":
            logger.info("Skipping execution for %s: NEUTRAL direction", request.stock_ticker)
            return None

        if request.confidence_score < 55:
            logger.info(
                "Skipping execution for %s: confidence %d%% < 55%% threshold",
                request.stock_ticker, request.confidence_score,
            )
            return None

        risk_params = self.RISK_MULTIPLIERS[request.risk_tolerance]
        atr = request.atr_14 or (request.current_price * 0.02)
        stop_distance = atr * risk_params["atr_stop"]

        if request.direction == "BULLISH":
            action = TradeAction.BUY
            stop_loss = request.current_price - stop_distance
            targets = self._bullish_targets(
                request.current_price, stop_distance,
                request.resistance_levels,
                [request.ma_50, request.ma_200],
                risk_params["rr_min"],
            )
            stop_rationale = f"ATR-based stop ({risk_params['atr_stop']}x ATR) below entry"
        else:  # BEARISH
            action = TradeAction.SELL
            stop_loss = request.current_price + stop_distance
            targets = self._bearish_targets(
                request.current_price, stop_distance,
                request.support_levels,
                [request.ma_50, request.ma_200],
                risk_params["rr_min"],
            )
            stop_rationale = f"ATR-based stop ({risk_params['atr_stop']}x ATR) above entry"

        if not targets:
            logger.warning("No valid targets for %s — R:R too low", request.stock_ticker)
            return None

        entry_price = request.current_price
        risk_amount = abs(entry_price - stop_loss)
        reward_amount = abs(targets[0] - entry_price)

        risk_reward = RiskRewardProfile(
            risk_amount=round(risk_amount, 4),
            reward_amount=round(reward_amount, 4),
            risk_reward_ratio=round(reward_amount / risk_amount, 2) if risk_amount > 0 else 0.0,
            risk_percent=round((risk_amount / entry_price) * 100, 2),
        )

        position_size_pct = self._position_size(
            risk_reward.risk_percent, request.confidence_score, risk_params["position_pct"]
        )
        timeframe = self._timeframe(request.confidence_score)
        setup_quality = self._grade(
            risk_reward.risk_reward_ratio,
            request.confidence_score,
            bool(request.support_levels or request.resistance_levels),
        )

        support_levels = [
            PriceLevel(price=lvl, rationale="Historical support", level_type="support")
            for lvl in request.support_levels[:3]
        ]
        resistance_levels = [
            PriceLevel(price=lvl, rationale="Historical resistance", level_type="resistance")
            for lvl in request.resistance_levels[:3]
        ]
        if request.ma_20:
            ma_level = PriceLevel(price=request.ma_20, rationale="20-day MA", level_type="ma")
            (support_levels if request.ma_20 < request.current_price else resistance_levels).append(ma_level)

        valid_days = 3 if timeframe == TradeTimeframe.SWING else 1

        return TradeExecution(
            stock_ticker=request.stock_ticker,
            generated_at=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=valid_days),
            prediction_id=request.prediction_id,
            action=action,
            order_type=OrderType.LIMIT,
            timeframe=timeframe,
            current_price=request.current_price,
            entry_price=round(entry_price, 4),
            entry_zone_low=round(entry_price * 0.995, 4),
            entry_zone_high=round(entry_price * 1.005, 4),
            stop_loss=round(stop_loss, 4),
            stop_loss_rationale=stop_rationale,
            take_profit_1=round(targets[0], 4),
            take_profit_2=round(targets[1], 4) if len(targets) > 1 else None,
            take_profit_3=round(targets[2], 4) if len(targets) > 2 else None,
            risk_reward=risk_reward,
            position_size_percent=position_size_pct,
            max_loss_percent=round(position_size_pct * (risk_reward.risk_percent / 100), 2),
            key_support_levels=support_levels,
            key_resistance_levels=resistance_levels,
            entry_conditions=self._entry_conditions(action, request.rsi_14, request.vwap, entry_price),
            invalidation_conditions=self._invalidation_conditions(action, stop_loss),
            setup_quality=setup_quality,
            confidence_score=request.confidence_score,
        )

    # ── helpers ────────────────────────────────────────────────────────────────

    def _bullish_targets(
        self,
        current: float,
        stop_distance: float,
        resistance: list[float],
        ma_levels: list[Optional[float]],
        min_rr: float,
    ) -> list[float]:
        min_target = current + stop_distance * min_rr
        targets: list[float] = []
        for lvl in sorted(resistance):
            if lvl >= min_target and len(targets) < 3:
                targets.append(lvl)
        for ma in ma_levels:
            if ma and ma >= min_target and ma not in targets and len(targets) < 3:
                targets.append(ma)
        for mult in (min_rr, min_rr * 1.5, min_rr * 2.0):
            if len(targets) >= 3:
                break
            t = current + stop_distance * mult
            if t not in targets:
                targets.append(t)
        return sorted(targets)[:3]

    def _bearish_targets(
        self,
        current: float,
        stop_distance: float,
        support: list[float],
        ma_levels: list[Optional[float]],
        min_rr: float,
    ) -> list[float]:
        min_target = current - stop_distance * min_rr
        targets: list[float] = []
        for lvl in sorted(support, reverse=True):
            if lvl <= min_target and len(targets) < 3:
                targets.append(lvl)
        for ma in ma_levels:
            if ma and ma <= min_target and ma not in targets and len(targets) < 3:
                targets.append(ma)
        for mult in (min_rr, min_rr * 1.5, min_rr * 2.0):
            if len(targets) >= 3:
                break
            t = current - stop_distance * mult
            if t not in targets:
                targets.append(t)
        return sorted(targets, reverse=True)[:3]

    def _position_size(self, risk_percent: float, confidence: int, base: float) -> float:
        conf_mult = confidence / 100
        risk_mult = 0.5 if risk_percent > 3 else 0.75 if risk_percent > 2 else 1.0
        return round(max(0.5, min(5.0, base * conf_mult * risk_mult)), 2)

    def _timeframe(self, confidence: int) -> TradeTimeframe:
        if confidence >= 60:
            return TradeTimeframe.SWING
        if confidence >= 40:
            return TradeTimeframe.INTRADAY
        return TradeTimeframe.SCALP

    def _grade(self, rr_ratio: float, confidence: int, has_confluence: bool) -> str:
        score = 0
        score += 3 if rr_ratio >= 3 else 2 if rr_ratio >= 2.5 else 1 if rr_ratio >= 2 else 0
        score += 3 if confidence >= 75 else 2 if confidence >= 60 else 1 if confidence >= 45 else 0
        if has_confluence:
            score += 1
        return "A+" if score >= 6 else "A" if score >= 4 else "B" if score >= 2 else "C"

    def _entry_conditions(
        self,
        action: TradeAction,
        rsi: Optional[float],
        vwap: Optional[float],
        price: float,
    ) -> list[str]:
        conditions = []
        if action == TradeAction.BUY:
            conditions.append("Price holds above entry zone for 15+ minutes")
            conditions.append("No significant resistance break attempt fails")
            if rsi and rsi < 70:
                conditions.append(f"RSI ({rsi:.0f}) not overbought")
            if vwap and price > vwap:
                conditions.append(f"Price above VWAP (${vwap:.2f})")
        else:
            conditions.append("Price holds below entry zone for 15+ minutes")
            conditions.append("No significant support bounce")
            if rsi and rsi > 30:
                conditions.append(f"RSI ({rsi:.0f}) not oversold")
            if vwap and price < vwap:
                conditions.append(f"Price below VWAP (${vwap:.2f})")
        conditions.append("Volume confirms direction (above average)")
        return conditions

    def _invalidation_conditions(self, action: TradeAction, stop_loss: float) -> list[str]:
        conditions = [
            f"Price closes beyond stop-loss (${stop_loss:.2f})",
            "Major news event changes fundamental outlook",
            "Broader market reverses sharply against position",
        ]
        if action == TradeAction.BUY:
            conditions.append("Bears take control with high-volume breakdown")
        else:
            conditions.append("Bulls take control with high-volume breakout")
        return conditions
