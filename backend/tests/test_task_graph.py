"""Tests for orchestration.task_graph."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from orchestration.task_graph import TaskGraph, TaskNode, TaskStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

def simple_graph() -> TaskGraph:
    """A → B → C (linear chain)."""
    g = TaskGraph()
    g.add_task("A", "agent_a")
    g.add_task("B", "agent_b", depends_on=["A"])
    g.add_task("C", "agent_c", depends_on=["B"])
    return g


def diamond_graph() -> TaskGraph:
    """Diamond: A splits to B and C which both feed D."""
    g = TaskGraph()
    g.add_task("A", "agent_a")
    g.add_task("B", "agent_b", depends_on=["A"])
    g.add_task("C", "agent_c", depends_on=["A"])
    g.add_task("D", "agent_d", depends_on=["B", "C"])
    return g


# ── add_task ──────────────────────────────────────────────────────────────────

class TestAddTask:
    def test_returns_task_node(self):
        g = TaskGraph()
        node = g.add_task("x", "agent_x")
        assert isinstance(node, TaskNode)
        assert node.id == "x"
        assert node.status == TaskStatus.PENDING

    def test_custom_max_retries(self):
        g = TaskGraph()
        node = g.add_task("x", "a", max_retries=3)
        assert node.max_retries == 3


# ── get_ready_tasks ───────────────────────────────────────────────────────────

class TestGetReadyTasks:
    def test_no_deps_immediately_ready(self):
        g = TaskGraph()
        g.add_task("A", "a")
        g.add_task("B", "b")
        ready_ids = {t.id for t in g.get_ready_tasks()}
        assert ready_ids == {"A", "B"}

    def test_dep_not_ready_until_parent_complete(self):
        g = simple_graph()
        ready = g.get_ready_tasks()
        assert {t.id for t in ready} == {"A"}

    def test_child_becomes_ready_after_parent_completes(self):
        g = simple_graph()
        g.get_ready_tasks()   # marks A as READY
        g.mark_running("A")
        g.mark_complete("A", "result_a")
        ready = g.get_ready_tasks()
        assert {t.id for t in ready} == {"B"}

    def test_running_task_not_in_ready(self):
        g = TaskGraph()
        g.add_task("A", "a")
        g.get_ready_tasks()
        g.mark_running("A")
        assert g.get_ready_tasks() == []


# ── mark_failed + retry + skip cascade ───────────────────────────────────────

class TestMarkFailed:
    def test_retry_resets_to_pending(self):
        g = simple_graph()
        g.get_ready_tasks()
        g.mark_running("A")
        g.mark_failed("A", "timeout")
        assert g._nodes["A"].status == TaskStatus.PENDING
        assert g._nodes["A"].retries == 1

    def test_exhausted_retries_marks_failed(self):
        g = simple_graph()
        g.add_task("A2", "a2", max_retries=0)   # no retries allowed
        g.mark_failed("A2", "error")
        assert g._nodes["A2"].status == TaskStatus.FAILED

    def test_cascade_skip_propagates(self):
        g = simple_graph()
        g._nodes["A"].max_retries = 0
        g.mark_failed("A", "boom")
        assert g._nodes["B"].status == TaskStatus.SKIPPED
        assert g._nodes["C"].status == TaskStatus.SKIPPED

    def test_cascade_skip_diamond(self):
        g = diamond_graph()
        g._nodes["A"].max_retries = 0
        g.mark_failed("A", "boom")
        for tid in ("B", "C", "D"):
            assert g._nodes[tid].status == TaskStatus.SKIPPED


# ── can_continue ──────────────────────────────────────────────────────────────

class TestCanContinue:
    def test_true_with_pending_tasks(self):
        g = simple_graph()
        assert g.can_continue() is True

    def test_false_when_all_complete(self):
        g = TaskGraph()
        g.add_task("A", "a")
        g.mark_complete("A", "r")
        assert g.can_continue() is False

    def test_false_when_all_skipped_or_failed(self):
        g = simple_graph()
        g._nodes["A"].max_retries = 0
        g.mark_failed("A", "err")
        assert g.can_continue() is False


# ── topological sort ──────────────────────────────────────────────────────────

class TestGetExecutionOrder:
    def test_linear_order(self):
        g = simple_graph()
        order = g.get_execution_order()
        assert order.index("A") < order.index("B")
        assert order.index("B") < order.index("C")

    def test_diamond_order(self):
        g = diamond_graph()
        order = g.get_execution_order()
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_cycle_raises(self):
        g = TaskGraph()
        g.add_task("X", "x", depends_on=["Y"])
        g.add_task("Y", "y", depends_on=["X"])
        with pytest.raises(ValueError, match="cycle"):
            g.get_execution_order()

    def test_has_cycle_false_for_dag(self):
        g = diamond_graph()
        assert g.has_cycle() is False

    def test_has_cycle_true_for_cyclic(self):
        g = TaskGraph()
        g.add_task("X", "x", depends_on=["Y"])
        g.add_task("Y", "y", depends_on=["X"])
        assert g.has_cycle() is True


# ── default graph ─────────────────────────────────────────────────────────────

class TestDefaultGraph:
    def test_builds_without_error(self):
        g = TaskGraph()
        g.build_default_graph()
        assert "blind_judge" in g._nodes
        assert "reconciler" in g._nodes
        assert "final_prediction" in g._nodes

    def test_no_cycle_in_default_graph(self):
        g = TaskGraph()
        g.build_default_graph()
        assert g.has_cycle() is False

    def test_initial_ready_tasks_are_leaf_agents(self):
        g = TaskGraph()
        g.build_default_graph()
        ready = {t.id for t in g.get_ready_tasks()}
        assert ready == {"macro_bull", "geo_bear", "quant"}


# ── get_summary ───────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_summary_fields(self):
        g = simple_graph()
        s = g.get_summary()
        assert s["total"] == 3
        assert s["can_continue"] is True
        assert "failed_tasks" in s

    def test_summary_counts_after_completion(self):
        g = TaskGraph()
        g.add_task("A", "a")
        g.mark_complete("A", "r")
        s = g.get_summary()
        assert s["counts"].get("COMPLETE") == 1
