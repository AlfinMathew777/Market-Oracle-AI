"""Tests for backtesting/data_guards.py — loader-boundary correctness guards."""

import pandas as pd
import pytest
from backtesting.data_guards import (
    MAX_EXIT_GAP_DAYS,
    exit_gap_ok,
    sane_close_price,
    validate_ohlc,
)


def _frame(rows, columns=("Open", "High", "Low", "Close")):
    return pd.DataFrame(rows, columns=list(columns))


# ── validate_ohlc ─────────────────────────────────────────────────────────────

def test_clean_bars_pass_through_unchanged():
    df = _frame([[10.0, 11.0, 9.5, 10.5], [10.5, 10.8, 10.1, 10.2]])
    out = validate_ohlc(df)
    assert len(out) == 2


def test_high_below_low_dropped():
    df = _frame([[10.0, 9.0, 11.0, 10.0], [10.0, 11.0, 9.5, 10.5]])
    out = validate_ohlc(df)
    assert len(out) == 1
    assert out.iloc[0]["High"] == 11.0


def test_high_fails_to_bracket_close_dropped():
    # close above high — structurally impossible
    df = _frame([[10.0, 10.5, 9.5, 11.0]])
    assert len(validate_ohlc(df)) == 0


def test_low_fails_to_bracket_open_dropped():
    # open below low — structurally impossible
    df = _frame([[9.0, 10.5, 9.5, 10.0]])
    assert len(validate_ohlc(df)) == 0


def test_nonpositive_price_dropped():
    df = _frame([[0.0, 1.0, 0.0, 0.5], [-1.0, 1.0, -2.0, 0.5], [10.0, 11.0, 9.5, 10.5]])
    out = validate_ohlc(df)
    assert len(out) == 1


def test_lowercase_columns_supported():
    df = _frame([[10.0, 9.0, 11.0, 10.0]], columns=("open", "high", "low", "close"))
    assert len(validate_ohlc(df)) == 0


def test_missing_columns_returned_as_is():
    df = pd.DataFrame({"Close": [10.0, -5.0]})
    out = validate_ohlc(df)
    assert len(out) == 2  # cannot validate — pass through untouched


def test_empty_frame_returned_as_is():
    df = pd.DataFrame()
    assert validate_ohlc(df).empty


def test_warn_strategy_keeps_rows():
    df = _frame([[10.0, 9.0, 11.0, 10.0]])
    out = validate_ohlc(df, strategy="warn")
    assert len(out) == 1


def test_raise_strategy_raises():
    df = _frame([[10.0, 9.0, 11.0, 10.0]])
    with pytest.raises(ValueError, match="violate OHLC invariants"):
        validate_ohlc(df, strategy="raise")


# ── exit_gap_ok ───────────────────────────────────────────────────────────────

def test_next_day_exit_ok():
    assert exit_gap_ok(pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-02"))


def test_weekend_gap_ok():
    # Friday → Monday = 3 calendar days
    assert exit_gap_ok(pd.Timestamp("2026-07-03"), pd.Timestamp("2026-07-06"))


def test_halt_gap_rejected():
    # 3-week halt must NOT count as a next-day outcome
    assert not exit_gap_ok(pd.Timestamp("2026-07-01"), pd.Timestamp("2026-07-22"))


def test_boundary_gap_exactly_max_ok():
    entry = pd.Timestamp("2026-07-01")
    assert exit_gap_ok(entry, entry + pd.Timedelta(days=MAX_EXIT_GAP_DAYS))


def test_same_day_exit_rejected():
    ts = pd.Timestamp("2026-07-01")
    assert not exit_gap_ok(ts, ts)


# ── sane_close_price ──────────────────────────────────────────────────────────

def test_sane_price_passes():
    assert sane_close_price(42.35) == 42.35


def test_zero_and_negative_rejected():
    assert sane_close_price(0.0) is None
    assert sane_close_price(-3.2) is None


def test_nan_and_inf_rejected():
    assert sane_close_price(float("nan")) is None
    assert sane_close_price(float("inf")) is None


def test_none_and_non_numeric_rejected():
    assert sane_close_price(None) is None
    assert sane_close_price("abc") is None
