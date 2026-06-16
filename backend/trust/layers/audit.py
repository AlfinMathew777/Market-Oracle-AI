"""Layer 5 — AUDIT: proves why.

The other layers decide; this layer makes the decision *permanent and provable*.
It writes the finished TrustCertificate to the hash-chained ledger BEFORE the
prediction is acted on (Article A1: "a decision that cannot be recorded cannot
be trusted").

Unlike layers 2-4, Audit does not run inside the normal `evaluate` pass — the
gateway invokes it explicitly after a certificate is assembled, because the audit
record IS the certificate. If the ledger write fails, the gateway downgrades the
decision to BLOCK (fail-closed): an unrecordable decision is not trustworthy.
"""

from __future__ import annotations

import logging

from trust.contracts import TrustCertificate, TrustContext
from trust.ledger import LedgerEntry, TrustLedger

logger = logging.getLogger(__name__)


class AuditLayer:
    name = "audit"

    def __init__(self, ledger: TrustLedger) -> None:
        self._ledger = ledger

    async def record(self, cert: TrustCertificate, ctx: TrustContext) -> LedgerEntry:
        """Append the certificate to the ledger. Raises on failure (caller fails closed)."""
        payload = cert.to_dict()
        payload["ticker"] = ctx.ticker
        # Compact, JSON-safe snapshot of the inputs so the decision is replayable (A2).
        payload["inputs"] = self._snapshot(ctx)
        entry = await self._ledger.append(
            payload,
            ticker=ctx.ticker,
            decision=cert.decision.value,
            trust_score=cert.trust_score,
            issued_at=cert.issued_at,
        )
        logger.info(
            "trust ledger: seq=%s ticker=%s decision=%s score=%s hash=%s",
            entry.seq, ctx.ticker, cert.decision.value, cert.trust_score, entry.entry_hash[:12],
        )
        return entry

    @staticmethod
    def _snapshot(ctx: TrustContext) -> dict:
        return {
            "ticker": ctx.ticker,
            "direction": ctx.direction,
            "confidence": round(ctx.confidence, 4),
            "signal_order": ctx.signal_order,
            "catalyst": ctx.catalyst,
            "agent_votes": ctx.agent_votes,
            "mc_stability": round(ctx.mc_stability, 4),
            "historical_accuracy": round(ctx.historical_accuracy, 4),
            "judge_result": ctx.judge_result,
            "data_feeds": ctx.data_feeds,
            "paper_mode": ctx.paper_mode,
        }
