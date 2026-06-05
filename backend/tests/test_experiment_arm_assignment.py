"""Tests for the dream-cycle A/B arm assignment.

The whole experiment depends on these properties holding:
- determinism across processes (Python's hash() is unsafe per PYTHONHASHSEED)
- approximately balanced split over many (ticker, date) tuples
- the salt actually re-shuffles assignments
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from experiment.arm_assignment import assign_arm, prompt_hash


class TestArmAssignmentDeterminism:
    """assign_arm must be deterministic across calls and process boundaries."""

    def test_same_input_returns_same_arm(self):
        d = datetime(2026, 5, 25, tzinfo=timezone.utc)
        results = {assign_arm("BHP.AX", d) for _ in range(50)}
        assert len(results) == 1, "non-deterministic: got multiple arms for same input"

    def test_different_tickers_can_split(self):
        d = datetime(2026, 5, 25, tzinfo=timezone.utc)
        arms = {t: assign_arm(t, d) for t in ("BHP.AX", "RIO.AX", "FMG.AX", "WDS.AX")}
        # not strictly required, but if everything is on one side something is wrong
        assert len(set(arms.values())) > 1, "all tickers landed on the same arm — bad hash"

    def test_default_predicted_at_uses_now(self):
        # Just verify it doesn't crash and returns a valid arm
        arm = assign_arm("BHP.AX")
        assert arm in ("T", "C")


class TestArmAssignmentBalance:
    """Over a meaningful sample, T/C split should be roughly 50/50."""

    def test_balance_across_year_of_ticker_dates(self):
        tickers = ["BHP.AX", "RIO.AX", "FMG.AX", "WDS.AX", "STO.AX", "CBA.AX",
                   "NAB.AX", "ANZ.AX", "WBC.AX", "MQG.AX", "CSL.AX", "TLS.AX"]
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        days = 252  # one trading year per ticker
        total = len(tickers) * days

        n_t = 0
        for t in tickers:
            for d in range(days):
                if assign_arm(t, start + timedelta(days=d)) == "T":
                    n_t += 1

        ratio = n_t / total
        # SHA-256 is well-distributed; tolerate 47-53% on N=3024
        assert 0.47 <= ratio <= 0.53, f"balance off: T ratio = {ratio:.3f} on N={total}"


class TestExperimentSalt:
    """Re-salting must produce a different assignment for the same (ticker, date)."""

    def test_different_salt_reshuffles(self):
        d = datetime(2026, 5, 25, tzinfo=timezone.utc)
        ticker = "BHP.AX"

        with patch.dict(os.environ, {"EXPERIMENT_SALT": "salt-A"}):
            arm_a = assign_arm(ticker, d)
        with patch.dict(os.environ, {"EXPERIMENT_SALT": "salt-B-very-different"}):
            arm_b = assign_arm(ticker, d)

        # Not guaranteed for any single ticker (chance of collision = 50%) — so we
        # test across many tickers and verify at least one flips.
        tickers = [f"TST{i}.AX" for i in range(20)]
        flipped = 0
        for t in tickers:
            with patch.dict(os.environ, {"EXPERIMENT_SALT": "salt-A"}):
                a = assign_arm(t, d)
            with patch.dict(os.environ, {"EXPERIMENT_SALT": "salt-B-very-different"}):
                b = assign_arm(t, d)
            if a != b:
                flipped += 1
        assert flipped > 0, "salt has no effect on assignment — broken hash input"
        # Half should flip on average; tolerate 25-75%
        assert 5 <= flipped <= 15, f"salt re-shuffle ratio off: {flipped}/20"


class TestPromptHash:
    """prompt_hash must be deterministic and key-order-independent."""

    def test_deterministic(self):
        ev = {"country": "AU", "event_type": "X", "fatalities": 0}
        assert prompt_hash(ev) == prompt_hash(ev)

    def test_key_order_independent(self):
        a = {"country": "AU", "event_type": "X"}
        b = {"event_type": "X", "country": "AU"}
        assert prompt_hash(a) == prompt_hash(b)

    def test_different_payload_different_hash(self):
        a = {"country": "AU"}
        b = {"country": "NZ"}
        assert prompt_hash(a) != prompt_hash(b)

    def test_returns_16_hex_chars(self):
        h = prompt_hash({"x": 1})
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)
