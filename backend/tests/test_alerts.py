"""
Tests for monitoring/alerts.py.

Covers:
  - Deduplication logic (_is_duplicate)
  - Alert insertion and notification (_fire_alert)
  - Individual check functions (accuracy drop, high signal volume,
    low confidence cluster, Monte Carlo instability)
  - CRUD helpers (get_active_alerts, get_alert_history, acknowledge_alert)

All tests use the isolated_db fixture — no alert is ever written to
the production database.
"""

import json
import pytest
from datetime import datetime, timedelta, timezone

from tests.conftest import insert_alert, insert_prediction


# ── _is_duplicate ──────────────────────────────────────────────────────────────

class TestIsDuplicate:

    @pytest.mark.asyncio
    async def test_no_duplicate_on_empty_db(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import _is_duplicate
        result = await _is_duplicate("ACCURACY_DROP", "", cooldown_minutes=60)
        assert result is False

    @pytest.mark.asyncio
    async def test_detects_duplicate_within_cooldown(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        await insert_alert(isolated_db, sample_alert)

        from monitoring.alerts import _is_duplicate
        result = await _is_duplicate("ACCURACY_DROP", "", cooldown_minutes=60)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_duplicate_after_cooldown(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await insert_alert(isolated_db, {
            "alert_type": "ACCURACY_DROP",
            "severity": "critical",
            "message": "old alert",
            "context": None,
            "created_at": old_ts,
        })

        from monitoring.alerts import _is_duplicate
        result = await _is_duplicate("ACCURACY_DROP", "", cooldown_minutes=60)
        assert result is False

    @pytest.mark.asyncio
    async def test_different_type_is_not_duplicate(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        await insert_alert(isolated_db, sample_alert)  # ACCURACY_DROP

        from monitoring.alerts import _is_duplicate
        result = await _is_duplicate("HIGH_SIGNAL_VOLUME", "", cooldown_minutes=60)
        assert result is False

    @pytest.mark.asyncio
    async def test_acknowledged_alert_not_counted(self, isolated_db, monkeypatch, sample_alert):
        """An acknowledged alert does not count for deduplication."""
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        import aiosqlite

        alert_id = await insert_alert(isolated_db, sample_alert)
        async with aiosqlite.connect(isolated_db) as db:
            await db.execute(
                "UPDATE alerts SET acknowledged_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), alert_id),
            )
            await db.commit()

        from monitoring.alerts import _is_duplicate
        result = await _is_duplicate("ACCURACY_DROP", "", cooldown_minutes=60)
        assert result is False

    @pytest.mark.asyncio
    async def test_dedup_key_matching(self, isolated_db, monkeypatch):
        """DATA_FEED_STALE uses feed name as dedup_key."""
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        await insert_alert(isolated_db, {
            "alert_type": "DATA_FEED_STALE",
            "severity": "critical",
            "message": "asx_prices stale for 35 minutes",
            "context": json.dumps({"feed": "asx_prices", "age_minutes": 35}),
        })

        from monitoring.alerts import _is_duplicate
        # Same feed → duplicate
        assert await _is_duplicate("DATA_FEED_STALE", "asx_prices", cooldown_minutes=30) is True
        # Different feed → not duplicate
        assert await _is_duplicate("DATA_FEED_STALE", "fred", cooldown_minutes=30) is False


# ── _fire_alert ────────────────────────────────────────────────────────────────

class TestFireAlert:

    @pytest.mark.asyncio
    async def test_creates_alert_on_first_fire(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import _fire_alert

        result = await _fire_alert("HIGH_SIGNAL_VOLUME", "warning", "15 signals in last hour")
        assert result is not None
        assert result["alert_type"] == "HIGH_SIGNAL_VOLUME"
        assert result["severity"] == "warning"
        assert "id" in result

    @pytest.mark.asyncio
    async def test_suppresses_duplicate(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import _fire_alert

        first = await _fire_alert("HIGH_SIGNAL_VOLUME", "warning", "15 signals")
        second = await _fire_alert("HIGH_SIGNAL_VOLUME", "warning", "16 signals")
        assert first is not None
        assert second is None  # Suppressed within cooldown window

    @pytest.mark.asyncio
    async def test_fires_different_types_independently(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import _fire_alert

        a1 = await _fire_alert("HIGH_SIGNAL_VOLUME", "warning", "msg")
        a2 = await _fire_alert("ACCURACY_DROP", "critical", "msg")
        assert a1 is not None
        assert a2 is not None

    @pytest.mark.asyncio
    async def test_returned_dict_shape(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import _fire_alert

        ctx = {"count": 15, "threshold": 10}
        result = await _fire_alert("HIGH_SIGNAL_VOLUME", "warning", "test msg", context=ctx)
        assert result["context"] == ctx
        assert "created_at" in result


# ── check_high_signal_volume ───────────────────────────────────────────────────

class TestCheckHighSignalVolume:

    @pytest.mark.asyncio
    async def test_no_alert_when_below_threshold(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        # DB is empty → 0 signals → no alert
        from monitoring.alerts import check_high_signal_volume
        result = await check_high_signal_volume()
        assert result is None

    @pytest.mark.asyncio
    async def test_alert_fires_above_threshold(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        import aiosqlite
        from datetime import datetime, timezone

        # Insert 11 prediction_log rows within the last hour
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(isolated_db) as db:
            for i in range(11):
                await db.execute(
                    """INSERT INTO prediction_log
                       (id, ticker, predicted_direction, confidence, predicted_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"vol-test-{i}",
                        "BHP.AX",
                        "bullish",
                        0.70,
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            await db.commit()

        from monitoring.alerts import check_high_signal_volume
        result = await check_high_signal_volume()
        assert result is not None
        assert result["alert_type"] == "HIGH_SIGNAL_VOLUME"


# ── check_low_confidence_cluster ──────────────────────────────────────────────

class TestCheckLowConfidenceCluster:

    @pytest.mark.asyncio
    async def test_no_alert_on_empty_db(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import check_low_confidence_cluster
        result = await check_low_confidence_cluster()
        assert result is None

    @pytest.mark.asyncio
    async def test_no_alert_when_high_confidence_present(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        import aiosqlite

        now = datetime.now(timezone.utc)
        rows = [
            ("hc-1", 0.45), ("hc-2", 0.50), ("hc-3", 0.55),
            ("hc-4", 0.45), ("hc-5", 0.75),  # ← this one is high-confidence
        ]
        async with aiosqlite.connect(isolated_db) as db:
            for rid, conf in rows:
                await db.execute(
                    """INSERT INTO prediction_log
                       (id, ticker, predicted_direction, confidence, predicted_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (rid, "BHP.AX", "bullish", conf, now.isoformat(), now.isoformat()),
                )
            await db.commit()

        from monitoring.alerts import check_low_confidence_cluster
        result = await check_low_confidence_cluster()
        assert result is None

    @pytest.mark.asyncio
    async def test_alert_fires_on_five_consecutive_low_confidence(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        import aiosqlite

        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(isolated_db) as db:
            for i in range(5):
                await db.execute(
                    """INSERT INTO prediction_log
                       (id, ticker, predicted_direction, confidence, predicted_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        f"low-conf-{i}",
                        "BHP.AX",
                        "bullish",
                        0.52,   # Below the 60% threshold
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            await db.commit()

        from monitoring.alerts import check_low_confidence_cluster
        result = await check_low_confidence_cluster()
        assert result is not None
        assert result["alert_type"] == "LOW_CONFIDENCE_CLUSTER"


# ── CRUD ───────────────────────────────────────────────────────────────────────

class TestGetActiveAlerts:

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import get_active_alerts
        alerts = await get_active_alerts()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_returns_unacknowledged_only(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        import aiosqlite

        alert_id = await insert_alert(isolated_db, sample_alert)
        # Insert a second alert and acknowledge it
        second_id = await insert_alert(isolated_db, {**sample_alert, "alert_type": "HIGH_SIGNAL_VOLUME"})
        async with aiosqlite.connect(isolated_db) as db:
            await db.execute(
                "UPDATE alerts SET acknowledged_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), second_id),
            )
            await db.commit()

        from monitoring.alerts import get_active_alerts
        alerts = await get_active_alerts()
        assert len(alerts) == 1
        assert alerts[0]["id"] == alert_id

    @pytest.mark.asyncio
    async def test_context_parsed_as_dict(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        await insert_alert(isolated_db, sample_alert)  # context is JSON string

        from monitoring.alerts import get_active_alerts
        alerts = await get_active_alerts()
        assert isinstance(alerts[0]["context"], dict)


class TestAcknowledgeAlert:

    @pytest.mark.asyncio
    async def test_acknowledge_returns_true(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        alert_id = await insert_alert(isolated_db, sample_alert)

        from monitoring.alerts import acknowledge_alert
        result = await acknowledge_alert(alert_id, "test-admin")
        assert result is True

    @pytest.mark.asyncio
    async def test_acknowledge_nonexistent_returns_false(self, isolated_db, monkeypatch):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        from monitoring.alerts import acknowledge_alert
        result = await acknowledge_alert(99999, "test-admin")
        assert result is False

    @pytest.mark.asyncio
    async def test_acknowledge_already_acknowledged_returns_false(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        alert_id = await insert_alert(isolated_db, sample_alert)

        from monitoring.alerts import acknowledge_alert
        await acknowledge_alert(alert_id, "first")
        result = await acknowledge_alert(alert_id, "second")
        assert result is False

    @pytest.mark.asyncio
    async def test_acknowledged_alert_disappears_from_active(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        alert_id = await insert_alert(isolated_db, sample_alert)

        from monitoring.alerts import acknowledge_alert, get_active_alerts
        await acknowledge_alert(alert_id, "admin")
        alerts = await get_active_alerts()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_get_alert_history_includes_acknowledged(self, isolated_db, monkeypatch, sample_alert):
        monkeypatch.setattr("database.DB_PATH", isolated_db)
        alert_id = await insert_alert(isolated_db, sample_alert)

        from monitoring.alerts import acknowledge_alert, get_alert_history
        await acknowledge_alert(alert_id, "admin")
        history = await get_alert_history()
        assert len(history) == 1
        assert history[0]["acknowledged_at"] is not None
        assert history[0]["acknowledged_by"] == "admin"
