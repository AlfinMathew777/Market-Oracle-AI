"""DAG-based task management for agent orchestration.

Each task is a node with zero or more dependency tasks that must complete
before it can run.  The graph supports topological ordering, cycle detection,
and incremental status tracking as tasks are dispatched and completed.

Default Market Oracle graph::

    macro_bull ──┐
    geo_bear   ──┼──► blind_judge ──► reconciler ──► final_prediction
    quant      ──┘

Usage::

    graph = TaskGraph()
    graph.build_default_graph()

    while graph.can_continue():
        ready = graph.get_ready_tasks()
        results = await asyncio.gather(*[run(t) for t in ready])
        for task, result in zip(ready, results):
            graph.mark_complete(task.id, result)
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class TaskNode:
    id: str
    agent_type: str
    depends_on: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    max_retries: int = 1
    result: Optional[Any] = None
    error: Optional[str] = None


class TaskGraph:
    """Directed-acyclic-graph of agent tasks with dependency resolution."""

    def __init__(self) -> None:
        self._nodes: Dict[str, TaskNode] = {}

    # ── Builder API ───────────────────────────────────────────────────────────

    def add_task(
        self,
        task_id: str,
        agent_type: str,
        depends_on: Optional[List[str]] = None,
        max_retries: int = 1,
    ) -> TaskNode:
        node = TaskNode(
            id=task_id,
            agent_type=agent_type,
            depends_on=depends_on or [],
            max_retries=max_retries,
        )
        self._nodes[task_id] = node
        return node

    def build_default_graph(self) -> None:
        """Populate the standard Market Oracle prediction pipeline graph."""
        self.add_task("macro_bull", "macro_bull_agent")
        self.add_task("geo_bear", "geo_bear_agent")
        self.add_task("quant", "quant_agent")
        self.add_task(
            "blind_judge",
            "blind_judge_agent",
            depends_on=["macro_bull", "geo_bear", "quant"],
        )
        self.add_task("reconciler", "reconciler_agent", depends_on=["blind_judge"])
        self.add_task("final_prediction", "final_prediction_agent", depends_on=["reconciler"])

    # ── Status transitions ────────────────────────────────────────────────────

    def mark_running(self, task_id: str) -> None:
        self._node(task_id).status = TaskStatus.RUNNING

    def mark_complete(self, task_id: str, result: Any) -> None:
        node = self._node(task_id)
        node.status = TaskStatus.COMPLETE
        node.result = result
        logger.debug("[TaskGraph] %s COMPLETE", task_id)

    def mark_failed(self, task_id: str, error: str) -> None:
        node = self._node(task_id)
        node.error = error
        if node.retries < node.max_retries:
            node.retries += 1
            node.status = TaskStatus.PENDING
            logger.warning("[TaskGraph] %s failed (retry %d/%d): %s", task_id, node.retries, node.max_retries, error)
        else:
            node.status = TaskStatus.FAILED
            logger.error("[TaskGraph] %s FAILED (no retries left): %s", task_id, error)
            self._cascade_skip(task_id)

    # ── Query API ─────────────────────────────────────────────────────────────

    def get_ready_tasks(self) -> List[TaskNode]:
        """Return all tasks whose dependencies are complete and are not yet running."""
        ready = []
        for node in self._nodes.values():
            if node.status not in (TaskStatus.PENDING, TaskStatus.READY):
                continue
            if self._deps_satisfied(node):
                node.status = TaskStatus.READY
                ready.append(node)
        return ready

    def can_continue(self) -> bool:
        """True if there are tasks that can still make progress."""
        return any(
            n.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING)
            for n in self._nodes.values()
        )

    def get_execution_order(self) -> List[str]:
        """Topological sort (Kahn's algorithm). Raises ValueError on cycle."""
        in_degree: Dict[str, int] = {nid: 0 for nid in self._nodes}
        for node in self._nodes.values():
            for dep in node.depends_on:
                in_degree[node.id] = in_degree.get(node.id, 0) + 1

        # Recalculate properly
        in_degree = {nid: 0 for nid in self._nodes}
        for node in self._nodes.values():
            for dep in node.depends_on:
                if dep in self._nodes:
                    in_degree[node.id] += 1

        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: List[str] = []

        while queue:
            current = queue.popleft()
            order.append(current)
            for node in self._nodes.values():
                if current in node.depends_on:
                    in_degree[node.id] -= 1
                    if in_degree[node.id] == 0:
                        queue.append(node.id)

        if len(order) != len(self._nodes):
            raise ValueError("TaskGraph contains a cycle — cannot determine execution order")
        return order

    def has_cycle(self) -> bool:
        try:
            self.get_execution_order()
            return False
        except ValueError:
            return True

    def get_summary(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        failed: List[str] = []
        for node in self._nodes.values():
            counts[node.status.value] = counts.get(node.status.value, 0) + 1
            if node.status == TaskStatus.FAILED:
                failed.append(node.id)
        return {
            "total": len(self._nodes),
            "counts": counts,
            "failed_tasks": failed,
            "can_continue": self.can_continue(),
        }

    def get_results(self) -> Dict[str, Any]:
        """Return completed task results keyed by task_id."""
        return {
            nid: node.result
            for nid, node in self._nodes.items()
            if node.status == TaskStatus.COMPLETE
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _node(self, task_id: str) -> TaskNode:
        if task_id not in self._nodes:
            raise KeyError(f"Unknown task: {task_id!r}")
        return self._nodes[task_id]

    def _deps_satisfied(self, node: TaskNode) -> bool:
        for dep_id in node.depends_on:
            dep = self._nodes.get(dep_id)
            if dep is None or dep.status != TaskStatus.COMPLETE:
                return False
        return True

    def _cascade_skip(self, failed_task_id: str) -> None:
        """Mark all descendants of a failed task as SKIPPED."""
        to_skip = {failed_task_id}
        changed = True
        while changed:
            changed = False
            for node in self._nodes.values():
                if node.id in to_skip:
                    continue
                if any(dep in to_skip for dep in node.depends_on):
                    node.status = TaskStatus.SKIPPED
                    to_skip.add(node.id)
                    changed = True
                    logger.warning("[TaskGraph] %s SKIPPED (upstream failure: %s)", node.id, failed_task_id)
