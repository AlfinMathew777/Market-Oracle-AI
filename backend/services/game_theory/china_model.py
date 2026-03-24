"""China Iron Ore Price-Based Strategy Model — Market Oracle AI

Price-based inference of China's current iron ore procurement strategy.
Uses only the iron ore spot price and daily change — no additional API calls.

Full PMI/geopolitical version (with FRED integration) is month-2 work.

Relevant tickers: BHP.AX, RIO.AX, FMG.AX, S32.AX
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ChinaSignal:
    strategy: str
    demand_direction: str
    confidence: float
    reasoning: str
    modifier: int


def analyse_china_strategy_from_price(
    iron_ore_price: Optional[float],
    iron_ore_change_pct: Optional[float],
    ticker: str,
) -> Optional[ChinaSignal]:
    """
    Infer China's current iron ore procurement strategy from spot price.

    Returns None for non-mining tickers (banks, LNG, gold).
    Returns ChinaSignal with strategy, demand_direction, and confidence modifier.

    Threshold logic (based on observed China procurement patterns):
      > $120/t  → stockpile drawdown — China draws on port inventories, delays spot buys
      < $90/t   → aggressive stockpiling — China builds strategic reserves at low prices
      falling sharply (< -2.5% today) → wait-and-see — delay purchases for better entry
      rising sharply (> +2.0% today)  → restocking signal — buyers returning
      $90–$120  → neutral monitoring — no clear strategic positioning
    """
    mining_tickers = {"BHP", "RIO", "FMG", "S32"}
    if not any(t in ticker for t in mining_tickers):
        return None

    if iron_ore_price is None:
        return None

    # Above $120 — China drawing down port stockpiles
    if iron_ore_price > 120:
        return ChinaSignal(
            strategy="stockpile_drawdown",
            demand_direction="bearish",
            confidence=65,
            reasoning=(
                f"Iron ore at ${iron_ore_price:.0f}/t — above $120 threshold. "
                f"China historical pattern: draw down port stockpiles, "
                f"reduce spot purchases to pressure prices lower. "
                f"Current level discourages restocking."
            ),
            modifier=-8,
        )

    # Below $90 — China stockpiling aggressively
    if iron_ore_price < 90:
        return ChinaSignal(
            strategy="aggressive_stockpiling",
            demand_direction="bullish",
            confidence=70,
            reasoning=(
                f"Iron ore at ${iron_ore_price:.0f}/t — below $90 threshold. "
                f"China historical pattern: build strategic reserves "
                f"aggressively at low prices. Demand uplift expected."
            ),
            modifier=+12,
        )

    # Price falling sharply today — China waits for lower entry
    if iron_ore_change_pct is not None and iron_ore_change_pct < -2.5:
        return ChinaSignal(
            strategy="wait_and_see",
            demand_direction="bearish",
            confidence=55,
            reasoning=(
                f"Iron ore falling {iron_ore_change_pct:.1f}% today. "
                f"China tactical pattern: delay purchases when prices "
                f"are falling sharply to secure better entry. "
                f"Short-term demand softness expected."
            ),
            modifier=-8,
        )

    # Price rising sharply — restocking signal
    if iron_ore_change_pct is not None and iron_ore_change_pct > 2.0:
        return ChinaSignal(
            strategy="restocking_signal",
            demand_direction="bullish",
            confidence=55,
            reasoning=(
                f"Iron ore rising {iron_ore_change_pct:.1f}% today. "
                f"Price strength suggests Chinese buyers are restocking. "
                f"Positive demand signal."
            ),
            modifier=+8,
        )

    # Price in normal range ($90–$120) — no strong strategic signal
    return ChinaSignal(
        strategy="neutral_monitoring",
        demand_direction="neutral",
        confidence=35,
        reasoning=(
            f"Iron ore at ${iron_ore_price:.0f}/t — within normal range. "
            f"No clear China strategic positioning signal."
        ),
        modifier=0,
    )
