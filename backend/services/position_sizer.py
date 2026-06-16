"""
Fractional-Kelly Position Sizing
--------------------------------
Sizes a position from the *historical* win-rate of similar predictions and the
trade's planned reward/risk ratio — instead of the legacy linear `confidence/100`
scaling that ignored track record entirely.

Why this exists:
- Kelly (`f = W - (1-W)/R`) is the long-run growth-optimal risk fraction, used by
  quantitative desks. But full Kelly is brutally sensitive to a mis-estimated W,
  so we apply a fractional (quarter-Kelly default) safety factor.
- A win-rate measured over a handful of resolved predictions is noise. We shrink
  it toward the *break-even* win-rate for the given payoff (a Bayesian prior),
  so an unproven setup earns no edge until the track record justifies it. This is
  the believability principle: weight must be earned by a measured track record.

Net effect: Kelly acts as a downsizer / circuit-breaker for weak or unproven
setups (small position or floor), while the firm's hard position cap remains the
binding constraint for strong, proven edges. Pure functions, no I/O — the caller
supplies the historical stats so this stays fully unit-testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Pseudo-observations of the break-even prior blended into a measured win-rate.
# 20 ≈ "treat a fresh ticker as having no edge until ~20 resolved predictions
# pull the estimate away from break-even".
_PRIOR_STRENGTH = 20.0

# Quarter-Kelly. Full Kelly maximises growth but is far too aggressive on noisy
# inputs; halving/quartering trades a little growth for much smaller drawdowns.
DEFAULT_KELLY_FRACTION = 0.25

# Floor matches TradeExecution.position_size_percent's lower bound (ge=0.5).
_MIN_POSITION_PCT = 0.5


@dataclass(frozen=True)
class KellyPositionResult:
    """Immutable result of a Kelly sizing computation, with full audit trail."""

    position_size_percent: float
    has_edge: bool
    win_rate_shrunk: float
    kelly_raw: float
    kelly_fractional: float
    rationale: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _breakeven_win_rate(payoff_ratio: float) -> float:
    """Win-rate at which a bet with this reward/risk ratio is exactly zero-EV."""
    return 1.0 / (1.0 + payoff_ratio)


def _shrink_win_rate(win_rate: float, sample_size: int, prior: float) -> float:
    """
    Blend a measured win-rate toward `prior` using pseudo-counts.

    With sample_size=0 the result is exactly `prior` (no edge assumed); as the
    sample grows the measured rate dominates.
    """
    n = max(0, sample_size)
    return (win_rate * n + prior * _PRIOR_STRENGTH) / (n + _PRIOR_STRENGTH)


def compute_kelly_position(
    *,
    win_rate_pct: float,
    sample_size: int,
    payoff_ratio: float,
    stop_risk_percent: float,
    max_position_pct: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    min_position_pct: float = _MIN_POSITION_PCT,
) -> KellyPositionResult:
    """
    Compute a fractional-Kelly position size as a percent of account equity.

    Args:
        win_rate_pct:      Historical hit-rate of comparable predictions (0-100).
        sample_size:       Number of resolved predictions behind that win-rate.
        payoff_ratio:      Planned reward/risk ratio (Kelly's R), e.g. 2.0.
        stop_risk_percent: Distance from entry to stop as % of entry price — how
                           much of the *position* is lost if stopped out.
        max_position_pct:  Hard cap from the caller's risk tolerance.
        kelly_fraction:    Safety fraction applied to raw Kelly (default 0.25).
        min_position_pct:  Floor returned when there is no edge.

    Returns:
        KellyPositionResult with the sized position and every intermediate value
        for the audit trail.
    """
    if payoff_ratio <= 0 or stop_risk_percent <= 0:
        return KellyPositionResult(
            position_size_percent=min_position_pct,
            has_edge=False,
            win_rate_shrunk=0.0,
            kelly_raw=0.0,
            kelly_fractional=0.0,
            rationale="Invalid payoff/stop inputs — defaulting to floor position.",
        )

    win_rate = _clamp(win_rate_pct / 100.0, 0.0, 1.0)
    prior = _breakeven_win_rate(payoff_ratio)
    win_rate_shrunk = _shrink_win_rate(win_rate, sample_size, prior)
    kelly_raw = win_rate_shrunk - (1.0 - win_rate_shrunk) / payoff_ratio

    if kelly_raw <= 0:
        return KellyPositionResult(
            position_size_percent=min_position_pct,
            has_edge=False,
            win_rate_shrunk=round(win_rate_shrunk, 4),
            kelly_raw=round(kelly_raw, 4),
            kelly_fractional=0.0,
            rationale=(
                f"No historical edge: shrunk win-rate {win_rate_shrunk:.1%} at "
                f"{payoff_ratio:.1f}:1 is below break-even {prior:.1%} "
                f"(n={sample_size}) — floor position."
            ),
        )

    kelly_fractional = kelly_raw * kelly_fraction

    # Map the Kelly *account-risk* fraction to a position size given the stop
    # distance. If stopped, account loss = (stop_risk_percent/100) * (P/100);
    # set that equal to kelly_fractional and solve for P.
    raw_position_pct = kelly_fractional * 10_000.0 / stop_risk_percent
    position_pct = _clamp(raw_position_pct, min_position_pct, max_position_pct)

    rationale = (
        f"Quarter-Kelly: shrunk win-rate {win_rate_shrunk:.1%} (n={sample_size}) "
        f"at {payoff_ratio:.1f}:1 → raw Kelly {kelly_raw:.3f} × {kelly_fraction} "
        f"= {kelly_fractional:.3f} account-risk → {position_pct:.2f}% position "
        f"(cap {max_position_pct:.1f}%)."
    )

    return KellyPositionResult(
        position_size_percent=round(position_pct, 2),
        has_edge=True,
        win_rate_shrunk=round(win_rate_shrunk, 4),
        kelly_raw=round(kelly_raw, 4),
        kelly_fractional=round(kelly_fractional, 4),
        rationale=rationale,
    )
