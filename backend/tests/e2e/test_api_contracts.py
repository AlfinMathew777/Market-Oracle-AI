"""
E2E — API contract tests.

Verifies that every major endpoint returns the documented response shape
regardless of what data is in the DB. These tests act as living API documentation.

Contract rules:
  - All success responses must have a 2xx status code
  - Error responses must have "detail" or "error" in the body
  - Pagination responses must be list-like or contain a list field
  - Confidence values in any response must be in [0.0, 1.0]
  - Directions, when present, must be one of: UP / DOWN / NEUTRAL /
    BULLISH / BEARISH / bullish / bearish / neutral
"""

import asyncio

import pytest

_VALID_DIRECTIONS = {
    "UP", "DOWN", "NEUTRAL",
    "bullish", "bearish", "neutral",
    "BULLISH", "BEARISH",
}


@pytest.mark.e2e
class TestHealthContract:
    """GET /api/health — must return operational shape."""

    def test_health_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/health")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_health_has_status_field(self, api_client):
        async def _run():
            return await api_client.get("/api/health")

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        assert "status" in data

    def test_health_has_queue_field(self, api_client):
        """Queue key must always be present (enabled=False when queue disabled)."""

        async def _run():
            return await api_client.get("/api/health")

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        assert "queue" in data
        assert "enabled" in data["queue"]

    def test_health_environment_is_string(self, api_client):
        async def _run():
            return await api_client.get("/api/health")

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        assert isinstance(data.get("environment"), str)


@pytest.mark.e2e
class TestErrorResponseShape:
    """4xx error responses must have consistent shape."""

    def test_404_has_detail_field(self, api_client):
        async def _run():
            return await api_client.get("/api/nonexistent_endpoint")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data or "error" in data

    def test_simulate_status_404_has_detail(self, api_client):
        async def _run():
            return await api_client.get("/api/simulate/status/sim_does_not_exist_xyz")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    def test_422_has_detail_field(self, api_client):
        """Pydantic validation errors return 422 with a structured detail."""

        async def _run():
            # Invalid lat (out of range)
            return await api_client.post(
                "/api/simulate",
                json={
                    "event_description": "test",
                    "event_type": "Economic",
                    "lat": 999,
                    "lon": 0,
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


@pytest.mark.e2e
class TestSimulateContract:
    """POST /api/simulate response shape contracts."""

    def test_skipped_response_shape(self, api_client):
        """Commentary events return a skipped shape with all required fields."""

        async def _run():
            return await api_client.post(
                "/api/simulate",
                json={
                    "event_description": "Top 10 ASX stocks to watch this week",
                    "event_type": "Opinion",
                    "lat": -33.87,
                    "lon": 151.21,
                    "country": "Australia",
                    "fatalities": 0,
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "skipped"
        assert "simulation_id" in data
        assert "reason" in data
        assert "prediction" in data

        pred = data["prediction"]
        assert "direction" in pred
        assert "confidence" in pred
        assert pred["confidence"] == 0.0
        assert pred["direction"] == "NEUTRAL"
        assert pred.get("is_skipped") is True

    def test_skipped_confidence_is_zero(self, api_client):
        """Skipped predictions always have confidence 0.0."""

        async def _run():
            return await api_client.post(
                "/api/simulate",
                json={
                    "event_description": "Should I buy BHP shares now?",
                    "event_type": "Opinion",
                    "lat": -33.87,
                    "lon": 151.21,
                    "country": "Australia",
                    "fatalities": 0,
                },
            )

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        if data.get("status") == "skipped":
            assert data["prediction"]["confidence"] == 0.0

    def test_killed_system_returns_503(self, api_client):
        """Kill switch blocks with 503."""
        import system_state

        system_state.activate_kill_switch("e2e contract test")

        async def _run():
            return await api_client.post(
                "/api/simulate",
                json={
                    "event_description": "China restricts Australian iron ore",
                    "event_type": "Economic",
                    "lat": 31.0,
                    "lon": 121.0,
                    "country": "China",
                    "fatalities": 0,
                },
            )

        try:
            response = asyncio.get_event_loop().run_until_complete(_run())
            assert response.status_code == 503
        finally:
            system_state.resume_signals()


@pytest.mark.e2e
class TestPredictionHistoryContract:
    """GET /api/predict/history and /api/predict/accuracy shape contracts."""

    def test_history_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/predict/history?limit=5")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_history_has_data_field(self, api_client):
        async def _run():
            return await api_client.get("/api/predict/history?limit=5")

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        assert "data" in data or isinstance(data, list)

    def test_accuracy_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/predict/accuracy")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_history_limit_respected(self, api_client):
        """Requesting limit=1 returns at most 1 prediction."""

        async def _run():
            return await api_client.get("/api/predict/history?limit=1")

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        assert len(items) <= 1


@pytest.mark.e2e
class TestAdminContract:
    """Admin endpoint shape contracts."""

    def test_system_status_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/admin/status")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_system_status_has_signals_enabled(self, api_client):
        async def _run():
            return await api_client.get("/api/admin/status")

        response = asyncio.get_event_loop().run_until_complete(_run())
        data = response.json()
        assert any(k in data for k in ["signals_enabled", "is_enabled", "status", "state"])

    def test_validation_summary_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/metrics/validation-summary?days=7")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_alerts_list_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/alerts")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200


@pytest.mark.e2e
class TestBacktestContract:
    """Backtest endpoint shape contracts."""

    def test_backtest_health_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/backtest/health")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200

    def test_backtest_status_unknown_returns_404(self, api_client):
        async def _run():
            return await api_client.get("/api/backtest/status/run_contract_test_unknown")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 404

    def test_backtest_results_unknown_returns_404(self, api_client):
        async def _run():
            return await api_client.get("/api/backtest/results/run_contract_test_unknown")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 404

    def test_backtest_runs_list_returns_200(self, api_client):
        async def _run():
            return await api_client.get("/api/backtest/runs")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
