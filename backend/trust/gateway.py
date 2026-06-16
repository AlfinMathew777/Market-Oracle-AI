"""The Trust Gateway — orchestrates the 5-layer defense-in-depth stack.

This is the single chokepoint every prediction passes through before it becomes
a signal. It does NOT re-implement any check — it runs the independent layers,
aggregates their verdicts into ONE trust score and ONE decision, applies the
tightest confidence cap, records a tamper-evident certificate, and returns it.

Decision logic (defense-in-depth — any layer can veto):
  1. Any layer veto (BLOCK finding / layer error)        → BLOCK
  2. Trust score < min_trust_score_actionable            → BLOCK
  3. Direction is NEUTRAL                                 → BLOCK (nothing to act on)
  4. Confidence capped below actionable floor            → BLOCK
  5. Any WARN finding OR score < degraded threshold      → APPROVE_DEGRADED
  6. Otherwise                                            → APPROVE

Fail-closed everywhere: a layer crash becomes a veto (handled in TrustLayer), and
a ledger write failure downgrades an APPROVE to BLOCK — absence of a green light
is a red light.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from trust.constitution import CONSTITUTION_VERSION, THRESHOLDS
from trust.contracts import (
    Decision,
    Finding,
    LayerVerdict,
    Severity,
    TrustCertificate,
    TrustContext,
)
from trust.layers.audit import AuditLayer
from trust.layers.evidence import EvidenceLayer
from trust.layers.risk import RiskLayer
from trust.layers.validation import ValidationLayer
from trust.ledger import TrustLedger

logger = logging.getLogger(__name__)


class TrustGateway:
    """Runs layers 2-5 over a prediction and issues a signed TrustCertificate."""

    def __init__(self, ledger: TrustLedger) -> None:
        self._ledger = ledger
        # Order matters for the audit narrative, not for correctness — layers are
        # independent. Evidence (truth) → Validation (quality) → Risk (action).
        self._layers = (EvidenceLayer(), ValidationLayer(), RiskLayer())
        self._audit = AuditLayer(ledger)

    async def evaluate(self, ctx: TrustContext) -> TrustCertificate:
        verdicts: list[LayerVerdict] = []
        for layer in self._layers:
            verdicts.append(await layer.evaluate(ctx))

        findings = tuple(f for v in verdicts for f in v.findings)
        trust_score = self._score(verdicts)
        confidence_out = self._capped_confidence(ctx, verdicts)
        decision = self._decide(ctx, verdicts, trust_score, confidence_out)
        direction_out = self._direction_out(ctx, decision)

        issued_at = datetime.now(UTC).isoformat()
        cert = TrustCertificate(
            decision=decision,
            trust_score=trust_score,
            confidence_in=ctx.confidence,
            confidence_out=confidence_out,
            direction_in=ctx.direction,
            direction_out=direction_out,
            constitution_version=CONSTITUTION_VERSION,
            layer_verdicts=tuple(verdicts),
            findings=findings,
            explain=self._explain(decision, trust_score, findings, ctx, confidence_out),
            issued_at=issued_at,
        )

        # Layer 5 — record before acting. A failed write fails the decision closed.
        try:
            entry = await self._audit.record(cert, ctx)
            cert = self._with_ledger(cert, entry.seq, entry.entry_hash)
        except Exception as e:  # noqa: BLE001
            logger.error("trust ledger append failed — failing decision closed: %s", e, exc_info=True)
            cert = self._fail_closed(cert)

        return cert

    # ── scoring & decision ───────────────────────────────────────────────────
    @staticmethod
    def _score(verdicts: list[LayerVerdict]) -> int:
        """Aggregate trust 0-100. Each WARN/BLOCK finding deducts its weighted cost."""
        score = 100.0
        for v in verdicts:
            for f in v.findings:
                if f.severity == Severity.WARN:
                    score -= 12.0 * f.weight
                elif f.severity == Severity.BLOCK:
                    score -= 100.0  # A single veto floors trust.
        return max(0, min(100, round(score)))

    @staticmethod
    def _capped_confidence(ctx: TrustContext, verdicts: list[LayerVerdict]) -> float:
        cap = min((v.confidence_cap for v in verdicts), default=1.0)
        cap = min(cap, THRESHOLDS.cap_absolute)
        return round(min(ctx.confidence, cap), 4)

    def _decide(self, ctx: TrustContext, verdicts: list[LayerVerdict],
                trust_score: int, confidence_out: float) -> Decision:
        if any(v.veto for v in verdicts):
            return Decision.BLOCK
        if trust_score < THRESHOLDS.min_trust_score_actionable:
            return Decision.BLOCK
        if ctx.direction.upper() == "NEUTRAL":
            return Decision.BLOCK
        if confidence_out < THRESHOLDS.min_confidence_actionable:
            return Decision.BLOCK
        has_warn = any(f.severity == Severity.WARN for v in verdicts for f in v.findings)
        if has_warn or trust_score < THRESHOLDS.degraded_trust_score \
                or confidence_out < ctx.confidence:
            return Decision.APPROVE_DEGRADED
        return Decision.APPROVE

    @staticmethod
    def _direction_out(ctx: TrustContext, decision: Decision) -> str:
        # The gateway never invents a direction; it only neutralises a blocked one
        # so downstream consumers cannot accidentally act on it.
        if decision == Decision.BLOCK:
            return "NEUTRAL"
        return ctx.direction.upper()

    # ── explanation & ledger stamping ────────────────────────────────────────
    @staticmethod
    def _explain(decision: Decision, score: int, findings: tuple[Finding, ...],
                 ctx: TrustContext, conf_out: float) -> str:
        head = f"{decision.value} · trust {score}/100 · {ctx.ticker} {ctx.direction}"
        if not findings:
            return f"{head} · clean pass on all layers."
        blocks = [f for f in findings if f.severity == Severity.BLOCK]
        warns = [f for f in findings if f.severity == Severity.WARN]
        parts = [head]
        if blocks:
            parts.append("BLOCKED BY: " + "; ".join(f"[{f.article}] {f.message}" for f in blocks))
        if warns:
            parts.append("CONCERNS: " + "; ".join(f"[{f.article}] {f.message}" for f in warns))
        if conf_out < ctx.confidence:
            parts.append(f"confidence capped {ctx.confidence:.0%} → {conf_out:.0%}.")
        return " · ".join(parts)

    @staticmethod
    def _with_ledger(cert: TrustCertificate, seq: int, h: str) -> TrustCertificate:
        from dataclasses import replace
        return replace(cert, ledger_seq=seq, ledger_hash=h)

    @staticmethod
    def _fail_closed(cert: TrustCertificate) -> TrustCertificate:
        from dataclasses import replace
        veto = Finding("AUDIT.LEDGER_WRITE_FAILED", Severity.BLOCK,
                       "Decision could not be recorded to the trust ledger — blocking.",
                       "audit", 1.0, "A1")
        return replace(
            cert,
            decision=Decision.BLOCK,
            direction_out="NEUTRAL",
            findings=cert.findings + (veto,),
            explain=cert.explain + " · BLOCKED: ledger write failed (fail-closed).",
        )
