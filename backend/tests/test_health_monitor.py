"""Tests for infrastructure.health_monitor."""

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from infrastructure.health_monitor import HealthMonitor, AgentHealth


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_monitor(**kwargs) -> HealthMonitor:
    return HealthMonitor(**kwargs)


# ── heartbeat ─────────────────────────────────────────────────────────────────

class TestHeartbeat:
    def test_registers_agent(self):
        m = make_monitor()
        m.heartbeat("agent_a")
        assert "agent_a" in m._records

    def test_updates_last_heartbeat(self):
        m = make_monitor()
        m.heartbeat("agent_a")
        t1 = m._records["agent_a"].last_heartbeat
        time.sleep(0.02)
        m.heartbeat("agent_a")
        t2 = m._records["agent_a"].last_heartbeat
        assert t2 > t1


# ── record_success / record_error ────────────────────────────────────────────

class TestRecordSuccessError:
    def test_success_clears_error_count(self):
        m = make_monitor(error_loop_threshold=3)
        m.heartbeat("a")
        m.record_error("a", RuntimeError("fail"))
        m.record_error("a", RuntimeError("fail"))
        m.record_success("a")
        assert m._records["a"].consecutive_errors == 0

    def test_errors_accumulate(self):
        m = make_monitor()
        m.heartbeat("a")
        for _ in range(3):
            m.record_error("a", RuntimeError("err"))
        assert m._records["a"].consecutive_errors == 3

    def test_last_error_stored(self):
        m = make_monitor()
        m.heartbeat("a")
        m.record_error("a", ValueError("boom"))
        assert "boom" in m._records["a"].last_error


# ── is_stuck ─────────────────────────────────────────────────────────────────

class TestIsStuck:
    def test_not_stuck_immediately(self):
        m = make_monitor(stuck_threshold=60)
        m.heartbeat("a")
        assert m.is_stuck("a") is False

    def test_stuck_after_threshold(self):
        m = make_monitor(stuck_threshold=0.05)
        m.heartbeat("a")
        time.sleep(0.1)
        assert m.is_stuck("a") is True

    def test_unknown_agent_not_stuck(self):
        m = make_monitor()
        assert m.is_stuck("unknown") is False


# ── is_error_loop ────────────────────────────────────────────────────────────

class TestIsErrorLoop:
    def test_not_loop_below_threshold(self):
        m = make_monitor(error_loop_threshold=3)
        m.heartbeat("a")
        m.record_error("a", Exception())
        m.record_error("a", Exception())
        assert m.is_error_loop("a") is False

    def test_loop_at_threshold(self):
        m = make_monitor(error_loop_threshold=3)
        m.heartbeat("a")
        for _ in range(3):
            m.record_error("a", Exception())
        assert m.is_error_loop("a") is True

    def test_unknown_agent_not_loop(self):
        m = make_monitor()
        assert m.is_error_loop("ghost") is False


# ── get_health_report ────────────────────────────────────────────────────────

class TestGetHealthReport:
    def test_healthy_agent(self):
        m = make_monitor()
        m.heartbeat("a")
        report = m.get_health_report()
        assert "a" in report
        health = report["a"]
        assert isinstance(health, AgentHealth)
        assert health.status == "healthy"
        assert health.recommendation == "continue"

    def test_error_loop_agent(self):
        m = make_monitor(error_loop_threshold=2)
        m.heartbeat("a")
        m.record_error("a", Exception())
        m.record_error("a", Exception())
        report = m.get_health_report()
        assert report["a"].status == "error_loop"
        assert report["a"].recommendation == "skip"

    def test_stuck_agent(self):
        m = make_monitor(stuck_threshold=0.05)
        m.heartbeat("a")
        time.sleep(0.1)
        report = m.get_health_report()
        assert report["a"].status == "stuck"
        assert report["a"].recommendation == "restart"


# ── get_unhealthy_agents ─────────────────────────────────────────────────────

class TestGetUnhealthyAgents:
    def test_healthy_not_in_list(self):
        m = make_monitor()
        m.heartbeat("a")
        assert "a" not in m.get_unhealthy_agents()

    def test_error_loop_in_list(self):
        m = make_monitor(error_loop_threshold=1)
        m.heartbeat("a")
        m.record_error("a", Exception())
        assert "a" in m.get_unhealthy_agents()

    def test_multiple_agents_mixed(self):
        m = make_monitor(error_loop_threshold=2, stuck_threshold=0.05)
        m.heartbeat("good")
        m.heartbeat("bad")
        m.record_error("bad", Exception())
        m.record_error("bad", Exception())
        unhealthy = m.get_unhealthy_agents()
        assert "bad" in unhealthy
        assert "good" not in unhealthy


# ── reset_agent ───────────────────────────────────────────────────────────────

class TestResetAgent:
    def test_reset_clears_errors(self):
        m = make_monitor(error_loop_threshold=1)
        m.heartbeat("a")
        m.record_error("a", Exception())
        assert m.is_error_loop("a") is True
        m.reset_agent("a")
        assert m.is_error_loop("a") is False
        assert m._records["a"].consecutive_errors == 0
