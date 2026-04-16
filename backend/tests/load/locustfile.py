"""Locust load test suite for Market Oracle AI.

Usage:
    # Interactive web UI (open http://localhost:8089)
    locust -f backend/tests/load/locustfile.py --host http://localhost:8000

    # Headless CI run (100 users, 10/s spawn, 2 min duration)
    locust -f backend/tests/load/locustfile.py --host http://localhost:8000 \
           --headless -u 100 -r 10 -t 2m \
           --html docs/load-report.html

    # Against staging
    locust -f backend/tests/load/locustfile.py \
           --host https://staging.asx.marketoracle.ai \
           --headless -u 50 -r 5 -t 5m

Environment variables:
    LOAD_TEST_API_KEY   — API key for authenticated endpoints (optional)

User classes:
    ReadOnlyUser    — Health + read endpoints only. High concurrency baseline.
    AnalyticsUser   — Reads + accuracy stats. Simulates dashboard consumers.
    SimulationUser  — Includes /api/simulate. Low spawn rate, high timeout.
"""

import os
import random
from locust import HttpUser, between, task, events

from tests.load.scenarios import (
    health_check,
    fetch_prediction_history,
    fetch_acled_events,
    fetch_asx_prices,
    fetch_chokepoint_risks,
    simulate_event,
    fetch_accuracy_stats,
)

_API_KEY = os.environ.get("LOAD_TEST_API_KEY", "")


# ── Performance thresholds (checked in on_quitting hook) ─────────────────────

_P95_THRESHOLD_MS = 2000    # read endpoints must answer within 2s at p95
_SIM_P95_MS       = 30_000  # simulation endpoint can take up to 30s at p95
_ERROR_RATE_MAX   = 0.05    # < 5% error rate acceptable


@events.quitting.add_listener
def assert_thresholds(environment, **_kwargs):
    """Fail the CI job if performance thresholds are breached."""
    stats = environment.stats
    failed = False

    for name, entry in stats.entries.items():
        if entry.num_requests == 0:
            continue

        p95 = entry.get_response_time_percentile(0.95)
        err_rate = entry.num_failures / entry.num_requests if entry.num_requests > 0 else 0

        threshold = _SIM_P95_MS if "simulate" in name[1] else _P95_THRESHOLD_MS

        if p95 > threshold:
            print(f"THRESHOLD BREACH: {name} p95={p95:.0f}ms > {threshold}ms")
            failed = True

        if err_rate > _ERROR_RATE_MAX:
            print(f"THRESHOLD BREACH: {name} error_rate={err_rate:.1%} > {_ERROR_RATE_MAX:.0%}")
            failed = True

    if failed:
        environment.process_exit_code = 1


# ── User classes ──────────────────────────────────────────────────────────────

class ReadOnlyUser(HttpUser):
    """
    Simulates a user consuming the public read-only endpoints.
    Heavy weight — most concurrent users will be of this type.

    Wait: 1-3 seconds between requests (aggressive read traffic).
    """
    weight = 7
    wait_time = between(1, 3)

    @task(3)
    def do_health(self):
        health_check(self.client)

    @task(5)
    def do_acled(self):
        fetch_acled_events(self.client)

    @task(4)
    def do_prices(self):
        fetch_asx_prices(self.client)

    @task(2)
    def do_chokepoints(self):
        fetch_chokepoint_risks(self.client)

    @task(3)
    def do_history(self):
        fetch_prediction_history(self.client)


class AnalyticsUser(HttpUser):
    """
    Simulates a power user viewing the accuracy dashboard and deep stats.
    Medium weight — fewer of these than read-only.

    Wait: 2-5 seconds (more thoughtful browsing).
    """
    weight = 2
    wait_time = between(2, 5)

    @task(2)
    def do_history(self):
        fetch_prediction_history(self.client)

    @task(3)
    def do_accuracy(self):
        fetch_accuracy_stats(self.client)

    @task(1)
    def do_health(self):
        health_check(self.client)

    @task(1)
    def do_chokepoints(self):
        fetch_chokepoint_risks(self.client)


class SimulationUser(HttpUser):
    """
    Simulates a user running event simulations (the most expensive path).
    Low weight — only a few concurrent simulation users to avoid overwhelming LLM quota.

    Wait: 10-30 seconds (simulate deliberate, spaced usage).
    """
    weight = 1
    wait_time = between(10, 30)

    @task(1)
    def do_simulate(self):
        simulate_event(self.client, api_key=_API_KEY)

    @task(3)
    def do_history_between_sims(self):
        """Read history while waiting between simulations."""
        fetch_prediction_history(self.client)
