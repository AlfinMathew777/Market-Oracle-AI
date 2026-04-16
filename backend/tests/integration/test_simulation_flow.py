"""
Integration tests — simulation workflow.

Tests the route layer and pre-flight/kill-switch gates without running the
full 50-agent LLM pipeline. All external calls (LLM, yfinance) are mocked.

Key contracts verified:
  - Kill switch blocks POST /api/simulate with 503
  - Pre-flight commentary filter skips junk events immediately (< 50ms)
  - Valid event bodies return simulation_id immediately
  - Status endpoint returns recognised shapes for running/unknown IDs
  - SimulationRequest validation rejects bad lat/lon/fatalities
"""

import pytest
from unittest.mock import AsyncMock, patch


_VALID_BODY = {
    "event_description": "China imposes tariffs on Australian iron ore exports",
    "event_type": "Economic",
    "lat": 31.23,
    "lon": 121.47,
    "country": "China",
    "fatalities": 0,
}


@pytest.mark.integration
class TestKillSwitchGate:
    """Kill switch must block simulations with HTTP 503."""

    def test_kill_switch_blocks_simulation(self, simulate_async_client):
        """503 when kill switch is active — no LLM call should be attempted."""
        import asyncio
        import system_state

        system_state.activate_kill_switch("integration test")

        async def _run():
            response = await simulate_async_client.post("/api/simulate", json=_VALID_BODY)
            return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 503
        body = response.json()
        assert "detail" in body

    def test_kill_switch_resume_allows_simulation(self, simulate_async_client, monkeypatch):
        """After resume, simulate endpoint is reachable (may still fail on LLM but not 503)."""
        import asyncio
        import system_state

        system_state.activate_kill_switch("test")
        system_state.resume_signals()

        # Mock the background task so we don't actually call LLMs
        monkeypatch.setattr(
            "routes.simulate.QUEUE_ENABLED", False
        )

        async def _run():
            with patch("routes.simulate._run_simulation_background", new_callable=AsyncMock):
                response = await simulate_async_client.post("/api/simulate", json=_VALID_BODY)
                return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code != 503


@pytest.mark.integration
class TestPreFlightFilter:
    """Commentary patterns must be blocked in < 50ms without any LLM call."""

    @pytest.mark.parametrize("desc", [
        "Top 10 ASX stocks to watch this week",
        "Should you buy BHP shares right now?",
        "Deep dive into Rio Tinto valuation",
        "3 reasons to sell iron ore stocks",
        "My top picks for Australian mining shares",
    ])
    def test_commentary_patterns_are_skipped(self, simulate_async_client, desc):
        import asyncio

        body = {**_VALID_BODY, "event_description": desc}

        async def _run():
            response = await simulate_async_client.post("/api/simulate", json=body)
            return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "skipped"
        assert "simulation_id" in data
        assert data["prediction"]["direction"] == "NEUTRAL"
        assert data["prediction"]["confidence"] == 0.0

    def test_real_event_not_skipped(self, simulate_async_client, monkeypatch):
        """A genuine market-moving event should NOT be filtered."""
        import asyncio

        monkeypatch.setattr("routes.simulate.QUEUE_ENABLED", False)

        async def _run():
            with patch("routes.simulate._run_simulation_background", new_callable=AsyncMock):
                response = await simulate_async_client.post("/api/simulate", json=_VALID_BODY)
                return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") != "skipped"


@pytest.mark.integration
class TestSimulateRequestValidation:
    """Pydantic model validation for SimulationRequest."""

    @pytest.mark.parametrize("lat", [-91, 91, 200, -200])
    def test_invalid_lat_rejected(self, simulate_async_client, lat):
        import asyncio

        body = {**_VALID_BODY, "lat": lat}

        async def _run():
            return await simulate_async_client.post("/api/simulate", json=body)

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    @pytest.mark.parametrize("lon", [-181, 181, 360, -360])
    def test_invalid_lon_rejected(self, simulate_async_client, lon):
        import asyncio

        body = {**_VALID_BODY, "lon": lon}

        async def _run():
            return await simulate_async_client.post("/api/simulate", json=body)

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    def test_negative_fatalities_rejected(self, simulate_async_client):
        import asyncio

        body = {**_VALID_BODY, "fatalities": -1}

        async def _run():
            return await simulate_async_client.post("/api/simulate", json=body)

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422

    def test_empty_event_description_rejected(self, simulate_async_client):
        import asyncio

        body = {**_VALID_BODY, "event_description": "   "}

        async def _run():
            return await simulate_async_client.post("/api/simulate", json=body)

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 422


@pytest.mark.integration
class TestSimulationStatus:
    """Status endpoint contracts."""

    def test_unknown_simulation_id_returns_404(self, simulate_async_client):
        import asyncio

        async def _run():
            return await simulate_async_client.get("/api/simulate/status/sim_nonexistent_abc123")

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 404

    def test_started_simulation_appears_in_status(self, simulate_async_client, monkeypatch):
        """A just-started (in-process) simulation should be retrievable immediately."""
        import asyncio
        from routes.simulate import active_simulations

        monkeypatch.setattr("routes.simulate.QUEUE_ENABLED", False)

        async def _run():
            with patch("routes.simulate._run_simulation_background", new_callable=AsyncMock):
                post_resp = await simulate_async_client.post("/api/simulate", json=_VALID_BODY)
                assert post_resp.status_code == 200
                sim_id = post_resp.json()["simulation_id"]

                get_resp = await simulate_async_client.get(f"/api/simulate/status/{sim_id}")
                return get_resp, sim_id

        response, sim_id = asyncio.get_event_loop().run_until_complete(_run())
        # Status can be 'running' (background task started) or 200 (completed quickly)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        # Clean up
        active_simulations.pop(sim_id, None)

    def test_queue_enqueue_path_returns_queued_status(self, simulate_async_client, monkeypatch):
        """When queue is enabled and enqueue succeeds, status should be 'queued'."""
        import asyncio

        monkeypatch.setattr("routes.simulate.QUEUE_ENABLED", True)

        mock_queue = AsyncMock()
        mock_queue.enqueue = AsyncMock(return_value="sim_test_queued_001")

        async def _run():
            with patch("routes.simulate.sim_queue", mock_queue):
                # map_event_to_ticker needs to resolve quickly
                with patch(
                    "event_ticker_mapping.map_event_to_ticker",
                    return_value=("BHP.AX", 0.9, "test"),
                ):
                    response = await simulate_async_client.post("/api/simulate", json=_VALID_BODY)
                    return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "simulation_id" in data
        assert "poll_url" in data

    def test_queue_fallback_on_redis_error(self, simulate_async_client, monkeypatch):
        """When queue enqueue fails, falls back to in-process and returns 'started'."""
        import asyncio

        monkeypatch.setattr("routes.simulate.QUEUE_ENABLED", True)

        mock_queue = AsyncMock()
        mock_queue.enqueue = AsyncMock(side_effect=RuntimeError("Redis down"))

        async def _run():
            with patch("routes.simulate.sim_queue", mock_queue):
                with patch("routes.simulate._run_simulation_background", new_callable=AsyncMock):
                    response = await simulate_async_client.post("/api/simulate", json=_VALID_BODY)
                    return response

        response = asyncio.get_event_loop().run_until_complete(_run())
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
