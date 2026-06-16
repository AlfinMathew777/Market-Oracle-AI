"""Base class for trust layers.

Every layer is a pure async function of a TrustContext → LayerVerdict. The base
class provides three guarantees so individual layers stay small and honest:

  1. TIMING — each evaluation is timed for the audit record.
  2. FAIL-CLOSED — if a layer raises, the base converts it into a *vetoing*
     verdict (Article R2). A layer that cannot prove safety blocks by default;
     a crash never silently approves a trade.
  3. UNIFORM SHAPE — helpers to build verdicts from a list of findings so the
     pass/score/cap arithmetic is identical across layers.

Subclasses implement `_check(ctx) -> list[Finding]` and optionally
`_confidence_cap(ctx, findings) -> float`.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from trust.contracts import Finding, LayerVerdict, Severity, TrustContext

logger = logging.getLogger(__name__)


class TrustLayer(ABC):
    """One independent layer in the defense-in-depth stack."""

    #: Stable layer name — must match a contracts.LAYER_* constant.
    name: str = "base"

    @abstractmethod
    async def _check(self, ctx: TrustContext) -> list[Finding]:
        """Return all findings for this prediction. Empty list == clean pass."""
        raise NotImplementedError

    def _confidence_cap(self, ctx: TrustContext, findings: list[Finding]) -> float:
        """Max confidence this layer permits. Override when a layer caps confidence."""
        return 1.0

    async def evaluate(self, ctx: TrustContext) -> LayerVerdict:
        """Run the layer with timing and fail-closed protection."""
        start = time.perf_counter()
        try:
            findings = await self._check(ctx)
            cap = self._confidence_cap(ctx, findings)
            return self._verdict(findings, cap, start)
        except Exception as e:  # noqa: BLE001 — fail-closed is the whole point.
            logger.error("trust layer %s crashed (failing closed): %s", self.name, e, exc_info=True)
            duration = (time.perf_counter() - start) * 1000
            veto = Finding(
                code=f"{self.name.upper()}.LAYER_ERROR",
                severity=Severity.BLOCK,
                message=f"{self.name} layer could not complete its check — blocking (fail-closed).",
                layer=self.name,
                weight=100.0,
                article="R2",
            )
            return LayerVerdict(
                layer=self.name,
                passed=False,
                score=0.0,
                confidence_cap=0.0,
                findings=(veto,),
                duration_ms=duration,
                error=str(e),
            )

    # ── helpers ──────────────────────────────────────────────────────────────
    def _verdict(self, findings: list[Finding], cap: float, start: float) -> LayerVerdict:
        duration = (time.perf_counter() - start) * 1000
        has_block = any(f.is_veto for f in findings)
        # Score starts at 1.0, each non-info finding deducts a normalised weight.
        deduction = sum(self._finding_cost(f) for f in findings)
        score = max(0.0, 1.0 - deduction)
        return LayerVerdict(
            layer=self.name,
            passed=not has_block,
            score=score,
            confidence_cap=max(0.0, min(1.0, cap)),
            findings=tuple(findings),
            duration_ms=duration,
        )

    @staticmethod
    def _finding_cost(f: Finding) -> float:
        if f.severity == Severity.INFO:
            return 0.0
        if f.severity == Severity.WARN:
            return min(0.5, 0.15 * f.weight)
        return 1.0  # BLOCK zeroes the layer score.
