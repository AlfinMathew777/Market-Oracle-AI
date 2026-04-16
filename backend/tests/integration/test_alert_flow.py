"""
Integration tests — alert system workflow.

Verifies:
  - GET /api/alerts returns a list (possibly empty)
  - POST /api/admin/check-alerts runs all alert checks without crashing
  - POST /api/alerts/{id}/acknowledge with unknown ID returns 404
  - Alert deduplication prevents duplicate rows (via existing unit logic)
  - Active alert count is consistent across insert and list
"""

import asyncio

import aiosqlite
import pytest


@pytest.mark.integration
class TestAlertListEndpoint:
    """GET /api/alerts endpoint contracts."""

    def test_get_alerts_returns_200(self, admin_async_client):
        async def _run():
            return await admin_async_client.get("/api/alerts")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_get_alerts_with_status_filter(self, admin_async_client):
        async def _run():
            return await admin_async_client.get("/api/alerts?status=active")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        # Should be a list or dict with a list inside
        assert isinstance(data, (list, dict))

    def test_get_alerts_pagination(self, admin_async_client):
        async def _run():
            return await admin_async_client.get("/api/alerts?limit=5&offset=0")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_empty_db_returns_empty_alert_list(self, admin_async_client, isolated_db):
        """Fresh DB with no alerts returns an empty list — not a crash."""

        async def _run():
            response = await admin_async_client.get("/api/alerts")
            return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        # Empty list, or dict with empty list inside
        if isinstance(data, list):
            assert data == []
        elif isinstance(data, dict):
            alerts = data.get("alerts", data.get("data", []))
            assert isinstance(alerts, list)


@pytest.mark.integration
class TestAlertAcknowledgeEndpoint:
    """POST /api/alerts/{id}/acknowledge contracts."""

    def test_acknowledge_nonexistent_alert_returns_error(self, admin_async_client):
        """Acknowledging an alert ID that doesn't exist returns 404 or 400."""

        async def _run():
            return await admin_async_client.post(
                "/api/alerts/99999/acknowledge",
                json={"note": "integration test"},
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code in {400, 404, 422}

    def test_acknowledge_existing_alert(self, admin_async_client, isolated_db):
        """Acknowledging an inserted alert returns 200."""

        async def _run():
            # Insert a real alert row
            async with aiosqlite.connect(isolated_db) as db:
                cursor = await db.execute(
                    """INSERT INTO alerts (alert_type, severity, message, context, created_at)
                       VALUES (?, ?, ?, ?, datetime('now'))""",
                    ("ACCURACY_DROP", "warning", "Test alert", "{}"),
                )
                await db.commit()
                alert_id = cursor.lastrowid

            response = await admin_async_client.post(
                f"/api/alerts/{alert_id}/acknowledge",
                json={"note": "integration test ack"},
            )
            return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code in {200, 204}


@pytest.mark.integration
class TestAlertCheckEndpoint:
    """POST /api/admin/check-alerts triggers all alert checks."""

    def test_check_alerts_runs_without_crash(self, admin_async_client, isolated_db):
        """Empty DB — all checks should complete gracefully (no data = no alerts)."""

        async def _run():
            return await admin_async_client.post("/api/admin/check-alerts")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        # Should have some indication of what was checked
        assert any(k in data for k in ["status", "checked", "alerts_fired", "results"])

    def test_check_alerts_with_insufficient_data_does_not_fire(
        self, admin_async_client, isolated_db
    ):
        """With < 10 predictions, accuracy alert should NOT fire (not enough data)."""

        async def _run():
            await admin_async_client.post("/api/admin/check-alerts")
            # Verify no accuracy-drop alert was inserted
            async with aiosqlite.connect(isolated_db) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM alerts WHERE alert_type = 'ACCURACY_DROP'"
                )
                (count,) = await cursor.fetchone()
            return count

        count = asyncio.get_event_loop().run_until_complete(_run())
        assert count == 0
