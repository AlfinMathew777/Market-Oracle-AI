"""Institutional Behaviour Classifier — Market Oracle AI

Classifies HIGH-VOLUME sessions into behavioural archetypes that predict
what happens NEXT, not just what is happening now.

Key insight: the same volume signal has opposite directional implications
depending on whether it is driven by conviction vs forced selling.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class InstitutionalSignal:
    behaviour_type: str
    direction_bias: str
    persistence: str
    confidence: float
    reasoning: str
    modifier: int


def classify_institutional_behaviour(
    volume_vs_avg: Optional[float],
    price_change_pct: Optional[float],
    has_critical_news: bool,
    consecutive_down_days: int,
    rsi: Optional[float],
    time_of_day_utc: Optional[int] = None,
) -> InstitutionalSignal:
    """
    Classify institutional behaviour from volume + price + context signals.

    Returns an InstitutionalSignal with:
      - behaviour_type: one of informed_selling, forced_selling, distribution,
                        institutional_accumulation, rebalancing, normal_volume,
                        unclassified_high_volume
      - direction_bias: bullish | bearish | neutral
      - persistence:    sustained | temporary | one_time | unknown
      - confidence:     0–100
      - reasoning:      human-readable explanation for agent prompts
      - modifier:       confidence delta to apply to final prediction (-25 to +25)
    """
    if not volume_vs_avg or volume_vs_avg < 1.5:
        return InstitutionalSignal(
            behaviour_type="normal_volume",
            direction_bias="neutral",
            persistence="unknown",
            confidence=30,
            reasoning="Normal volume — no significant institutional activity.",
            modifier=0,
        )

    is_selling    = price_change_pct is not None and price_change_pct < -0.5
    is_buying     = price_change_pct is not None and price_change_pct > 0.5
    is_open_close = time_of_day_utc in {0, 1, 5, 6} if time_of_day_utc is not None else False
    is_oversold   = rsi is not None and rsi < 30
    is_extreme    = volume_vs_avg >= 3.0

    # Pattern 1: Informed selling — conviction bearish
    # High vol + price down + critical news = smart money reacting to news
    if volume_vs_avg >= 2.0 and is_selling and has_critical_news:
        return InstitutionalSignal(
            behaviour_type="informed_selling",
            direction_bias="bearish",
            persistence="sustained",
            confidence=75,
            reasoning=(
                f"HIGH VOLUME ({volume_vs_avg:.1f}x) + price down "
                f"({price_change_pct:.1f}%) + critical news = "
                f"informed institutional selling. "
                f"Expect continued selling pressure."
            ),
            modifier=-15,
        )

    # Pattern 2: Forced selling — contrarian bullish
    # High vol + price down + NO news + RSI oversold = redemption or margin call
    # Guard: extreme volume + sustained downtrend = distribution (Pattern 3), not forced selling
    is_distribution = is_extreme and consecutive_down_days >= 2
    if volume_vs_avg >= 2.0 and is_selling and not has_critical_news and is_oversold and not is_distribution:
        return InstitutionalSignal(
            behaviour_type="forced_selling",
            direction_bias="bullish",
            persistence="temporary",
            confidence=60,
            reasoning=(
                f"HIGH VOLUME ({volume_vs_avg:.1f}x) + price down "
                f"+ RSI oversold ({rsi:.0f}) + NO news catalyst = "
                f"forced/redemption selling. "
                f"When forced selling exhausts → price rebounds. "
                f"Contrarian opportunity — not conviction bearish."
            ),
            modifier=+10,
        )

    # Pattern 3: Distribution — sustained bearish
    # Extreme vol + selling + multiple down days = systematic offloading
    if is_extreme and is_selling and consecutive_down_days >= 2:
        return InstitutionalSignal(
            behaviour_type="distribution",
            direction_bias="bearish",
            persistence="sustained",
            confidence=70,
            reasoning=(
                f"EXTREME VOLUME ({volume_vs_avg:.1f}x) during "
                f"sustained downtrend ({consecutive_down_days} down days) = "
                f"institutional distribution phase. "
                f"Large holders systematically reducing positions."
            ),
            modifier=-12,
        )

    # Pattern 4: Accumulation — bullish
    # High vol + price up after multiple down days = smart money buying weakness
    if volume_vs_avg >= 2.0 and is_buying and consecutive_down_days >= 3:
        return InstitutionalSignal(
            behaviour_type="institutional_accumulation",
            direction_bias="bullish",
            persistence="sustained",
            confidence=65,
            reasoning=(
                f"HIGH VOLUME ({volume_vs_avg:.1f}x) + price up "
                f"after {consecutive_down_days} consecutive down days = "
                f"smart money buying weakness. "
                f"Typically precedes sustained recovery."
            ),
            modifier=+12,
        )

    # Pattern 5: Rebalancing — neutral, no follow-through
    if volume_vs_avg >= 2.0 and is_open_close:
        return InstitutionalSignal(
            behaviour_type="rebalancing",
            direction_bias="neutral",
            persistence="one_time",
            confidence=50,
            reasoning=(
                f"High volume at market open/close = "
                f"mechanical portfolio rebalancing. "
                f"No directional conviction — no follow-through expected."
            ),
            modifier=0,
        )

    # Default: unclassified high volume
    direction = "bearish" if is_selling else ("bullish" if is_buying else "neutral")
    return InstitutionalSignal(
        behaviour_type="unclassified_high_volume",
        direction_bias=direction,
        persistence="unknown",
        confidence=40,
        reasoning=f"High volume ({volume_vs_avg:.1f}x) — behaviour pattern unclear.",
        modifier=-5 if is_selling else (5 if is_buying else 0),
    )
