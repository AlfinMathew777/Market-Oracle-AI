"""Tests for the backend/data_sources/ alternative-data package.

All external I/O (HTTP, yfinance, asyncpraw) is mocked — tests are fast
and never touch real APIs.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data_sources.base import DataPoint, _mem_get, _mem_set
from data_sources.asx_announcements import ASXAnnouncements, _PATTERNS
from data_sources.asic_insider import ASICInsider
from data_sources.analyst_recommendations import AnalystRecommendations
from data_sources.rba_macro import RBAMacro, _SECTOR_RATE_SENSITIVITY
from data_sources.reddit_sentiment import RedditSentiment
from data_sources.aggregator import DataAggregator, _SOURCE_WEIGHTS


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_point(source="test", ticker="BHP.AX", signal=0.5, confidence=0.8) -> DataPoint:
    return DataPoint(
        source=source,
        ticker=ticker,
        timestamp=datetime.now(timezone.utc),
        category="test",
        signal_strength=signal,
        confidence=confidence,
        raw_data={},
        summary=f"{ticker}: test point",
    )


# ── DataPoint ─────────────────────────────────────────────────────────────────

def test_datapoint_to_dict_keys():
    point = _make_point()
    d = point.to_dict()
    assert {"source", "ticker", "timestamp", "category", "signal_strength", "confidence", "summary"}.issubset(d.keys())
    assert "raw_data" not in d  # raw_data excluded from serialised form


def test_datapoint_signal_strength_in_range():
    for signal in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        p = _make_point(signal=signal)
        assert -1.0 <= p.signal_strength <= 1.0


# ── In-memory cache (base) ─────────────────────────────────────────────────────

def test_mem_cache_set_and_get():
    _mem_set("_test_key", "hello", ttl_seconds=60)
    assert _mem_get("_test_key") == "hello"


def test_mem_cache_expires():
    import time
    _mem_set("_expire_key", "gone", ttl_seconds=0)
    # TTL=0 means it expires immediately on next monotonic check
    time.sleep(0.01)
    assert _mem_get("_expire_key") is None


# ── ASXAnnouncements ──────────────────────────────────────────────────────────

SAMPLE_HTML = """
<html><body><table>
  <tr>
    <td>17/04/2026</td><td></td>
    <td>BHP announces profit upgrade for FY2026</td>
  </tr>
  <tr>
    <td>16/04/2026</td><td></td>
    <td>BHP trading halt announced</td>
  </tr>
  <tr>
    <td>15/04/2026</td><td></td>
    <td>Appendix 4C quarterly report</td>
  </tr>
</table></body></html>
"""

@pytest.mark.asyncio
async def test_asx_announcements_parses_html():
    source = ASXAnnouncements()
    cutoff = datetime.now() - timedelta(days=30)
    points = source._parse_html(SAMPLE_HTML, "BHP.AX", cutoff)

    assert len(points) == 3
    categories = {p.category for p in points}
    assert "profit_upgrade" in categories
    assert "trading_halt" in categories
    assert "quarterly" in categories


@pytest.mark.asyncio
async def test_asx_announcements_profit_upgrade_signal_positive():
    source = ASXAnnouncements()
    cutoff = datetime.now() - timedelta(days=30)
    points = source._parse_html(SAMPLE_HTML, "BHP.AX", cutoff)
    upgrade = next(p for p in points if p.category == "profit_upgrade")
    assert upgrade.signal_strength > 0


@pytest.mark.asyncio
async def test_asx_announcements_trading_halt_signal_negative():
    source = ASXAnnouncements()
    cutoff = datetime.now() - timedelta(days=30)
    points = source._parse_html(SAMPLE_HTML, "BHP.AX", cutoff)
    halt = next(p for p in points if p.category == "trading_halt")
    assert halt.signal_strength < 0


@pytest.mark.asyncio
async def test_asx_announcements_http_failure_returns_empty():
    source = ASXAnnouncements()
    import httpx
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        points = await source.fetch("BHP.AX")
    assert points == []


@pytest.mark.asyncio
async def test_asx_announcements_cutoff_filters_old():
    source = ASXAnnouncements()
    # Only today's cutoff — older announcements in HTML should be excluded
    cutoff = datetime.now() - timedelta(days=1)
    # All three HTML rows are 17, 16, 15 Apr — one is within 1 day, two outside
    points = source._parse_html(SAMPLE_HTML, "BHP.AX", cutoff)
    assert len(points) == 1  # only 17/04/2026 passes


@pytest.mark.asyncio
async def test_asx_announcements_price_sensitive_flag_boosts_confidence():
    html = """
    <html><body><table>
      <tr class="pricesensitive">
        <td>17/04/2026</td><td></td><td>Dividend announcement</td>
      </tr>
    </table></body></html>
    """
    source = ASXAnnouncements()
    cutoff = datetime.now() - timedelta(days=30)
    points = source._parse_html(html, "WBC.AX", cutoff)
    assert len(points) == 1
    assert points[0].confidence == 0.80


# ── ASICInsider ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_asic_insider_net_buy_produces_bullish_point():
    source = ASICInsider()
    with patch.object(source, "_fetch_sync", return_value=(50_000.0, 2, 0)):
        points = await source.fetch("BHP.AX")
    assert len(points) == 1
    assert points[0].signal_strength > 0
    assert points[0].category == "insider_buy"


@pytest.mark.asyncio
async def test_asic_insider_net_sell_produces_bearish_point():
    source = ASICInsider()
    with patch.object(source, "_fetch_sync", return_value=(-80_000.0, 0, 3)):
        points = await source.fetch("BHP.AX")
    assert len(points) == 1
    assert points[0].signal_strength < 0
    assert points[0].category == "insider_sell"


@pytest.mark.asyncio
async def test_asic_insider_below_threshold_returns_empty():
    source = ASICInsider()
    with patch.object(source, "_fetch_sync", return_value=(5_000.0, 1, 0)):
        points = await source.fetch("BHP.AX")
    assert points == []


@pytest.mark.asyncio
async def test_asic_insider_multiple_directors_boost_signal():
    source = ASICInsider()
    # Single director
    with patch.object(source, "_fetch_sync", return_value=(50_000.0, 1, 0)):
        single = await source.fetch("BHP.AX")
    # Two directors
    with patch.object(source, "_fetch_sync", return_value=(50_000.0, 2, 0)):
        multi = await source.fetch("BHP.AX")
    assert multi[0].signal_strength > single[0].signal_strength


@pytest.mark.asyncio
async def test_asic_insider_yfinance_failure_returns_empty():
    source = ASICInsider()
    with patch.object(source, "_fetch_sync", side_effect=Exception("yfinance down")):
        points = await source.fetch("BHP.AX")
    assert points == []


# ── AnalystRecommendations ────────────────────────────────────────────────────

def _make_summary_df(sb=5, b=10, h=5, s=2, ss=1):
    import pandas as pd
    return pd.DataFrame([{
        "strongBuy": sb, "buy": b, "hold": h, "sell": s, "strongSell": ss
    }])


@pytest.mark.asyncio
async def test_analyst_recommendations_bullish_consensus():
    source = AnalystRecommendations()
    summary = _make_summary_df(sb=8, b=12, h=3, s=1, ss=0)
    with patch.object(source, "_fetch_sync", return_value={"summary": summary, "upgrades_downgrades": None}):
        points = await source.fetch("BHP.AX")
    assert any(p.category == "analyst_consensus" and p.signal_strength > 0 for p in points)


@pytest.mark.asyncio
async def test_analyst_recommendations_handles_empty_summary():
    source = AnalystRecommendations()
    import pandas as pd
    with patch.object(source, "_fetch_sync", return_value={"summary": pd.DataFrame(), "upgrades_downgrades": None}):
        points = await source.fetch("BHP.AX")
    assert points == []


@pytest.mark.asyncio
async def test_analyst_recommendations_handles_none_data():
    source = AnalystRecommendations()
    with patch.object(source, "_fetch_sync", return_value=None):
        points = await source.fetch("BHP.AX")
    assert points == []


@pytest.mark.asyncio
async def test_analyst_recommendations_upgrade_produces_bullish():
    import pandas as pd
    from datetime import datetime, timezone
    source = AnalystRecommendations()
    idx = pd.DatetimeIndex([datetime.now(timezone.utc)])
    upgrades_df = pd.DataFrame(
        [{"Firm": "Goldman", "FromGrade": "Hold", "ToGrade": "Buy", "Action": "up"}],
        index=idx,
    )
    summary = _make_summary_df()
    with patch.object(source, "_fetch_sync", return_value={"summary": summary, "upgrades_downgrades": upgrades_df}):
        points = await source.fetch("BHP.AX")
    upgrade_points = [p for p in points if p.category == "analyst_upgrade"]
    assert len(upgrade_points) == 1
    assert upgrade_points[0].signal_strength > 0


# ── RBAMacro ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rba_macro_rate_rising_bullish_for_banks():
    source = RBAMacro()
    mock_rba = {
        "cash_rate": 4.35,
        "meeting_today": False,
        "last_decision": {"title": "RBA raises cash rate", "summary": "Board increased rate"},
    }
    with patch.object(source, "_get_rba_status", return_value=mock_rba):
        points = await source.fetch("CBA.AX", sector="Financials")
    assert len(points) == 1
    assert points[0].signal_strength > 0  # Banks benefit from rate hikes


@pytest.mark.asyncio
async def test_rba_macro_rate_rising_bearish_for_reits():
    source = RBAMacro()
    mock_rba = {
        "cash_rate": 4.35,
        "meeting_today": False,
        "last_decision": {"title": "Rate hike", "summary": "increased"},
    }
    with patch.object(source, "_get_rba_status", return_value=mock_rba):
        points = await source.fetch("GMG.AX", sector="Real Estate")
    assert len(points) == 1
    assert points[0].signal_strength < 0


@pytest.mark.asyncio
async def test_rba_macro_meeting_today_boosts_confidence():
    source = RBAMacro()
    mock_rba_no_meeting = {"cash_rate": 4.35, "meeting_today": False, "last_decision": {"title": "increase", "summary": ""}}
    mock_rba_meeting = {"cash_rate": 4.35, "meeting_today": True, "last_decision": {"title": "increase", "summary": ""}}
    with patch.object(source, "_get_rba_status", return_value=mock_rba_no_meeting):
        points_no = await source.fetch("CBA.AX", sector="Financials")
    with patch.object(source, "_get_rba_status", return_value=mock_rba_meeting):
        points_yes = await source.fetch("CBA.AX", sector="Financials")
    assert points_yes[0].confidence > points_no[0].confidence


@pytest.mark.asyncio
async def test_rba_macro_service_failure_returns_empty():
    source = RBAMacro()
    with patch.object(source, "_get_rba_status", side_effect=Exception("network")):
        points = await source.fetch("CBA.AX", sector="Financials")
    assert points == []


# ── RedditSentiment ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reddit_sentiment_returns_empty_when_unconfigured():
    source = RedditSentiment()
    with patch.dict("os.environ", {}, clear=True):
        # Force REDDIT_CLIENT_ID to be missing
        import os
        old = os.environ.pop("REDDIT_CLIENT_ID", None)
        old2 = os.environ.pop("REDDIT_CLIENT_SECRET", None)
        try:
            points = await source.fetch("BHP.AX")
        finally:
            if old:
                os.environ["REDDIT_CLIENT_ID"] = old
            if old2:
                os.environ["REDDIT_CLIENT_SECRET"] = old2
    assert points == []


# ── DataAggregator ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aggregator_handles_partial_source_failure():
    agg = DataAggregator()

    # Patch individual sources — asx_announcements fails, others return one point each
    mock_asx = AsyncMock(side_effect=Exception("scrape failed"))
    mock_insider = AsyncMock(return_value=[_make_point("asic_insider", signal=0.6, confidence=0.7)])
    mock_analyst = AsyncMock(return_value=[_make_point("analyst_recommendations", signal=0.4, confidence=0.6)])
    mock_rba = AsyncMock(return_value=[])
    mock_reddit = AsyncMock(return_value=[])

    agg._sources["asx_announcements"].fetch_cached = mock_asx
    agg._sources["asic_insider"].fetch_cached = mock_insider
    agg._sources["analyst_recommendations"].fetch_cached = mock_analyst
    agg._sources["rba_macro"].fetch_cached = mock_rba
    agg._sources["reddit_sentiment"].fetch_cached = mock_reddit

    data = await agg.gather_all("BHP.AX")
    # Should not raise; failed source → empty list
    assert data["asx_announcements"] == []
    assert len(data["asic_insider"]) == 1
    assert len(data["analyst_recommendations"]) == 1


def test_aggregator_aggregate_signal_empty_data():
    agg = DataAggregator()
    composite = agg.aggregate_signal({
        "asx_announcements": [],
        "asic_insider": [],
        "analyst_recommendations": [],
        "rba_macro": [],
        "reddit_sentiment": [],
    })
    assert composite["signal"] == 0.0
    assert composite["confidence"] == 0.0
    assert composite["source_count"] == 0


def test_aggregator_aggregate_signal_weighting():
    """Higher-weighted source should dominate the composite signal."""
    agg = DataAggregator()
    # ASX announcements (weight 0.30) say strong bullish (+1.0)
    # Reddit (weight 0.10) says strong bearish (-1.0)
    data = {
        "asx_announcements": [_make_point("asx_announcements", signal=1.0, confidence=0.9)],
        "asic_insider": [],
        "analyst_recommendations": [],
        "rba_macro": [],
        "reddit_sentiment": [_make_point("reddit_sentiment", signal=-1.0, confidence=0.9)],
    }
    composite = agg.aggregate_signal(data)
    # Net should be positive because asx_announcements outweighs reddit
    assert composite["signal"] > 0


def test_aggregator_source_weights_sum_at_most_one():
    total = sum(_SOURCE_WEIGHTS.values())
    assert total <= 1.0, f"Source weights sum to {total:.3f} — must be ≤ 1.0"


def test_aggregator_summaries_populated():
    agg = DataAggregator()
    data = {
        "asx_announcements": [_make_point("asx_announcements", signal=0.5)],
        "asic_insider": [],
        "analyst_recommendations": [],
        "rba_macro": [],
        "reddit_sentiment": [],
    }
    composite = agg.aggregate_signal(data)
    assert len(composite["summaries"]) == 1
    assert "BHP.AX" in composite["summaries"][0]
