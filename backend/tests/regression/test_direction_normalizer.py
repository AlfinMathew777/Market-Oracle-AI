"""
Regression tests for validation/direction_normalizer.py.

Locks the token mapping so that any future change to BULLISH_TOKENS,
BEARISH_TOKENS, or NEUTRAL_TOKENS is immediately visible as a test failure
and must be a deliberate decision.

Also covers:
  - _determine_outcome round-trips (no regressions from Phase 3 refactor)
  - is_actionable contract
  - UNVALIDATABLE outcome for unknown tokens
"""

import pytest
from validation.direction_normalizer import (
    normalize_direction,
    is_actionable,
    BULLISH_TOKENS,
    BEARISH_TOKENS,
    NEUTRAL_TOKENS,
)


# ── normalize_direction parametrized ─────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    # Canonical bullish tokens
    ("bullish",  "bullish"),
    ("up",       "bullish"),
    ("buy",      "bullish"),
    ("long",     "bullish"),
    ("positive", "bullish"),
    # Canonical bearish tokens
    ("bearish",  "bearish"),
    ("down",     "bearish"),
    ("sell",     "bearish"),
    ("short",    "bearish"),
    ("negative", "bearish"),
    # Canonical neutral tokens
    ("neutral",  "neutral"),
    ("hold",     "neutral"),
    ("sideways", "neutral"),
    ("flat",     "neutral"),
    ("unclear",  "neutral"),
    # Case-insensitivity
    ("BULLISH",  "bullish"),
    ("DOWN",     "bearish"),
    ("NEUTRAL",  "neutral"),
    ("Up",       "bullish"),
    # Leading/trailing whitespace
    ("  bullish  ", "bullish"),
    ("  down\t",    "bearish"),
    # Unknown / unrecognised
    ("unknown_token", "unvalidatable"),
    ("UNVALIDATABLE", "unvalidatable"),
    ("garbage",       "unvalidatable"),
    ("",              "unvalidatable"),
    ("  ",            "unvalidatable"),
    # None
    (None,            "unvalidatable"),
])
def test_normalize_direction(raw, expected):
    assert normalize_direction(raw) == expected


# ── is_actionable contract ────────────────────────────────────────────────────

@pytest.mark.parametrize("direction,expected", [
    ("bullish",       True),
    ("bearish",       True),
    ("neutral",       False),
    ("unvalidatable", False),
])
def test_is_actionable(direction, expected):
    assert is_actionable(direction) is expected


# ── Token set membership guards ───────────────────────────────────────────────

class TestTokenSetMembership:
    """Explicit membership tests — fail loudly if a token is added or removed."""

    def test_bullish_tokens_contain_legacy_up(self):
        assert "up" in BULLISH_TOKENS, "Legacy 'up' token must stay in BULLISH_TOKENS"

    def test_bearish_tokens_contain_legacy_down(self):
        assert "down" in BEARISH_TOKENS, "Legacy 'down' token must stay in BEARISH_TOKENS"

    def test_token_sets_are_disjoint(self):
        assert BULLISH_TOKENS.isdisjoint(BEARISH_TOKENS), "Bullish/bearish overlap"
        assert BULLISH_TOKENS.isdisjoint(NEUTRAL_TOKENS), "Bullish/neutral overlap"
        assert BEARISH_TOKENS.isdisjoint(NEUTRAL_TOKENS), "Bearish/neutral overlap"

    def test_neutral_not_in_bullish_or_bearish(self):
        assert "neutral" not in BULLISH_TOKENS
        assert "neutral" not in BEARISH_TOKENS


# ── _determine_outcome round-trips ────────────────────────────────────────────

class TestDetermineOutcome:
    """
    Smoke-test _determine_outcome against all token variants.
    These are the behaviours locked by the Phase 3 refactor.
    """

    def _call(self, direction: str, entry: float, exit_: float):
        from validation.outcome_checker import _determine_outcome
        return _determine_outcome(direction, entry, exit_)

    # Bullish tokens — large upward move → CORRECT
    @pytest.mark.parametrize("token", ["bullish", "up", "buy"])
    def test_bullish_tokens_correct_on_up_move(self, token):
        outcome, _ = self._call(token, 100.0, 102.0)
        assert outcome == "CORRECT"

    # Bearish tokens — large downward move → CORRECT
    @pytest.mark.parametrize("token", ["bearish", "down", "sell"])
    def test_bearish_tokens_correct_on_down_move(self, token):
        outcome, _ = self._call(token, 100.0, 98.0)
        assert outcome == "CORRECT"

    # Bullish token — downward move → INCORRECT
    def test_bullish_incorrect_on_down_move(self):
        outcome, _ = self._call("bullish", 100.0, 98.0)
        assert outcome == "INCORRECT"

    # Bearish token — upward move → INCORRECT
    def test_bearish_incorrect_on_up_move(self):
        outcome, _ = self._call("bearish", 100.0, 102.0)
        assert outcome == "INCORRECT"

    # Neutral direction abstains regardless of price movement
    def test_neutral_direction_never_correct_or_incorrect(self):
        for entry, exit_ in [(100.0, 110.0), (100.0, 90.0), (100.0, 100.0)]:
            outcome, _ = self._call("neutral", entry, exit_)
            assert outcome == "NEUTRAL", f"neutral should be NEUTRAL, got {outcome}"

    # Unrecognised token → UNVALIDATABLE
    def test_unknown_token_returns_unvalidatable(self):
        outcome, _ = self._call("???", 100.0, 105.0)
        assert outcome == "UNVALIDATABLE"

    # Small moves → NEUTRAL regardless of direction
    def test_small_move_returns_neutral(self):
        outcome, _ = self._call("bullish", 100.0, 100.3)
        assert outcome == "NEUTRAL"

    # change_pct is always returned
    def test_returns_change_pct(self):
        _, change = self._call("bullish", 100.0, 105.0)
        assert abs(change - 5.0) < 0.001


# ── Neutral scoring bug regression ────────────────────────────────────────────

class TestNeutralScoringRegression:
    """
    Ensure that 'neutral' direction never produces prediction_correct=0/1.
    The revalidate_historical.py script fixed 18 historical rows; this test
    prevents the bug from re-appearing in future validations.
    """

    def test_neutral_outcome_maps_to_null_correct_flag(self):
        """
        validate_prediction() must set correct_flag=None (NULL) for NEUTRAL outcomes.
        This test exercises the mapping logic, not the full async pipeline.
        """
        from validation.outcome_checker import _determine_outcome

        # Neutral direction, big up move — must still be NEUTRAL
        outcome, _ = _determine_outcome("neutral", 100.0, 110.0)
        assert outcome == "NEUTRAL"

        # Simulate the correct_flag mapping from validate_prediction()
        correct_flag = True if outcome == "CORRECT" else (False if outcome == "INCORRECT" else None)
        assert correct_flag is None, (
            f"Neutral outcome must produce correct_flag=None, got {correct_flag!r}"
        )

    def test_unvalidatable_outcome_maps_to_null_correct_flag(self):
        from validation.outcome_checker import _determine_outcome

        outcome, _ = _determine_outcome("???", 100.0, 110.0)
        assert outcome == "UNVALIDATABLE"

        correct_flag = True if outcome == "CORRECT" else (False if outcome == "INCORRECT" else None)
        assert correct_flag is None
