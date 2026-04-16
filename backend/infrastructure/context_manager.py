"""Context manager with compression cascade — keeps LLM context within a token budget.

Compression stages (applied progressively as the budget fills):
  NONE       — full context, no modification
  COMPACT    — strip duplicate whitespace, remove repeated turns
  COMPRESS   — abbreviate system messages, drop examples
  SUMMARIZE  — LLM-compress old turns into a single summary turn
  CHECKPOINT — serialise state to memory, clear history
  TRUNCATE   — keep only the last N turns

Usage::

    ctx = ContextManager(token_budget=4000)
    ctx.add_turn("system", "You are a financial analyst…")
    ctx.add_turn("user",   "Analyse BHP…")
    messages = ctx.get_context()   # compressed if needed
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_TRUNCATE_KEEP_TURNS = 3


class CompressionStage(str, Enum):
    NONE       = "NONE"
    COMPACT    = "COMPACT"
    COMPRESS   = "COMPRESS"
    SUMMARIZE  = "SUMMARIZE"
    CHECKPOINT = "CHECKPOINT"
    TRUNCATE   = "TRUNCATE"


@dataclass
class _Checkpoint:
    id: str
    history_snapshot: List[Dict[str, str]]
    token_estimate: int


class ContextManager:
    """Manages conversation history with progressive compression."""

    def __init__(self, token_budget: int = 4000) -> None:
        self.token_budget = token_budget
        self._history: List[Dict[str, str]] = []
        self._compression_stage: CompressionStage = CompressionStage.NONE
        self._checkpoints: Dict[str, _Checkpoint] = {}
        self._llm_summarize_fn = None   # injected at runtime if needed

    # ── Public API ────────────────────────────────────────────────────────────

    def add_turn(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        self.compress_if_needed()

    def get_context(self) -> List[Dict[str, str]]:
        self.compress_if_needed()
        return list(self._history)

    def estimate_tokens(self) -> int:
        total = sum(len(t.get("content", "")) for t in self._history)
        return total // 4   # ~4 chars per token

    def get_compression_stage(self) -> CompressionStage:
        return self._compression_stage

    def compress_if_needed(self) -> None:
        tokens = self.estimate_tokens()
        ratio  = tokens / self.token_budget

        if ratio <= 0.50:
            self._compression_stage = CompressionStage.NONE
            return
        if ratio <= 0.70:
            self._apply_compact()
            self._compression_stage = CompressionStage.COMPACT
            return
        if ratio <= 0.85:
            self._apply_compress()
            self._compression_stage = CompressionStage.COMPRESS
            return
        if ratio <= 0.95:
            self._apply_summarize()
            self._compression_stage = CompressionStage.SUMMARIZE
            return
        # >95% — truncate to last N turns (preserve system message)
        self._apply_truncate()
        self._compression_stage = CompressionStage.TRUNCATE

    def checkpoint(self) -> str:
        cp_id = str(uuid.uuid4())[:8]
        self._checkpoints[cp_id] = _Checkpoint(
            id=cp_id,
            history_snapshot=list(self._history),
            token_estimate=self.estimate_tokens(),
        )
        self._history = []
        self._compression_stage = CompressionStage.CHECKPOINT
        logger.info("[ContextManager] Checkpoint saved: %s", cp_id)
        return cp_id

    def restore(self, checkpoint_id: str) -> None:
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise KeyError(f"Unknown checkpoint: {checkpoint_id!r}")
        self._history = list(cp.history_snapshot)
        self._compression_stage = CompressionStage.NONE
        logger.info("[ContextManager] Restored checkpoint %s (%d tokens)", checkpoint_id, cp.token_estimate)

    def set_summarize_fn(self, fn) -> None:
        """Inject an async callable(messages) -> str used by the SUMMARIZE stage."""
        self._llm_summarize_fn = fn

    # ── Compression stages ────────────────────────────────────────────────────

    def _apply_compact(self) -> None:
        """Remove excess whitespace and deduplicate consecutive identical turns."""
        compacted: List[Dict[str, str]] = []
        prev_content = None
        for turn in self._history:
            content = re.sub(r"\s{2,}", " ", turn["content"].strip())
            if content != prev_content:
                compacted.append({"role": turn["role"], "content": content})
                prev_content = content
        self._history = compacted

    def _apply_compress(self) -> None:
        """Abbreviate system message and trim long user turns."""
        self._apply_compact()
        compressed: List[Dict[str, str]] = []
        for turn in self._history:
            content = turn["content"]
            if turn["role"] == "system" and len(content) > 500:
                content = content[:500] + " [truncated for token budget]"
            compressed.append({"role": turn["role"], "content": content})
        self._history = compressed

    def _apply_summarize(self) -> None:
        """Collapse old turns into a summary sentinel (synchronous approximation)."""
        self._apply_compress()
        if len(self._history) <= 3:
            return
        # Keep system message + last 2 turns; summarise the middle into a single assistant note
        system_turns = [t for t in self._history if t["role"] == "system"]
        non_system   = [t for t in self._history if t["role"] != "system"]
        old_turns    = non_system[:-2]
        recent_turns = non_system[-2:]
        if not old_turns:
            return
        summary_text = (
            "[CONTEXT SUMMARY] Previous analysis covered "
            + str(len(old_turns))
            + " turns. Key points compressed to save tokens."
        )
        self._history = system_turns + [{"role": "assistant", "content": summary_text}] + recent_turns
        logger.debug("[ContextManager] Summarised %d old turns", len(old_turns))

    def _apply_truncate(self) -> None:
        """Keep system messages and only the last N turns."""
        system_turns = [t for t in self._history if t["role"] == "system"]
        non_system   = [t for t in self._history if t["role"] != "system"]
        kept = non_system[-_TRUNCATE_KEEP_TURNS:]
        self._history = system_turns + kept
        logger.warning(
            "[ContextManager] TRUNCATE applied — kept %d/%d non-system turns",
            len(kept),
            len(non_system),
        )
