"""Unit tests for services.context_budget — defensive text truncation."""

import pytest

from services.context_budget import (
    DEFAULT_HEADLINE_CHARS,
    total_chars,
    truncate_text,
)


def test_truncate_text_shorter_than_limit_unchanged():
    text = "Iron ore demand surges on China stimulus"
    assert truncate_text(text, 200) == text


def test_truncate_text_equal_to_limit_unchanged():
    text = "x" * 50
    assert truncate_text(text, 50) == text


def test_truncate_text_longer_than_limit_is_bounded():
    text = "word " * 200  # 1000 chars
    out = truncate_text(text, 100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_truncate_text_snaps_to_word_boundary():
    # 'supercalifragilistic' should not be sliced mid-word when a space is near the cut.
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    out = truncate_text(text, 30)
    assert len(out) <= 30
    # No partial trailing word (last char before suffix is a full word, not a fragment)
    assert "…" in out
    body = out[:-1].rstrip()
    assert not body.endswith("lambd")  # did not hard-cut mid-word when space available


def test_truncate_text_hard_cut_when_no_space():
    text = "x" * 500  # no spaces at all
    out = truncate_text(text, 20)
    assert len(out) <= 20
    assert out.endswith("…")


def test_truncate_text_none_returns_empty():
    assert truncate_text(None, 200) == ""


def test_truncate_text_empty_returns_empty():
    assert truncate_text("", 200) == ""


def test_truncate_text_zero_or_negative_limit_returns_empty():
    assert truncate_text("hello world", 0) == ""
    assert truncate_text("hello world", -5) == ""


def test_truncate_text_strips_surrounding_whitespace():
    assert truncate_text("   tidy   ", 200) == "tidy"


def test_default_headline_chars_is_reasonable():
    # Guard against accidental edits that would let huge headlines through.
    assert 50 <= DEFAULT_HEADLINE_CHARS <= 400


def test_total_chars_sums_and_ignores_none():
    assert total_chars("abc", None, "de") == 5
    assert total_chars() == 0
    assert total_chars(None, None) == 0
