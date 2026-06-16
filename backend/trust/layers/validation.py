"""Layer 3 — VALIDATION: checks quality.

Given that the prediction is *true* (Evidence passed), is it *good enough to act
on*? This layer judges statistical quality: confidence floors, agent consensus
strength, Monte Carlo stability, calibration against the per-order caps, and the
system's own track record.

It also computes this layer's `confidence_cap` — the maximum confidence the
prediction is allowed to keep given its signal order and the absolute ceiling
(Article V4). The gateway applies the tightest cap across all layers.
"""

from __future__ import annotations

from trust.constitution import THRESHOLDS
from trust.contracts import Finding, Severity, TrustContext
from trust.layers.base import TrustLayer


class ValidationLayer(TrustLayer):
    name = "validation"

    async def _check(self, ctx: TrustContext) -> list[Finding]:
        findings: list[Finding] = []
        findings += self._check_confidence(ctx)
        findings += self._check_consensus(ctx)
        findings += self._check_stability(ctx)
        findings += self._check_track_record(ctx)
        return findings

    # ── V1: confidence floor ─────────────────────────────────────────────────
    def _check_confidence(self, ctx: TrustContext) -> list[Finding]:
        if ctx.direction.upper() == "NEUTRAL":
            return []
        if ctx.confidence < THRESHOLDS.min_confidence_monitor:
            return [Finding("VALID.CONF_BELOW_MONITOR", Severity.BLOCK,
                            f"Confidence {ctx.confidence:.0%} below monitor floor "
                            f"{THRESHOLDS.min_confidence_monitor:.0%}.",
                            self.name, 1.0, "V1")]
        if ctx.confidence < THRESHOLDS.min_confidence_actionable:
            return [Finding("VALID.CONF_BELOW_ACTIONABLE", Severity.BLOCK,
                            f"Confidence {ctx.confidence:.0%} below actionable floor "
                            f"{THRESHOLDS.min_confidence_actionable:.0%} — monitor only.",
                            self.name, 1.0, "V1")]
        return []

    # ── V2: agent consensus ──────────────────────────────────────────────────
    def _check_consensus(self, ctx: TrustContext) -> list[Finding]:
        votes = ctx.agent_votes or {}
        bull = int(votes.get("bull", votes.get("bullish", 0)))
        bear = int(votes.get("bear", votes.get("bearish", 0)))
        neut = int(votes.get("neut", votes.get("neutral", 0)))
        total = bull + bear + neut
        if total == 0:
            return []  # No agent vote data to judge — other layers carry it.
        dominant = max(bull, bear, neut)
        share = dominant / total
        if share < THRESHOLDS.min_agent_consensus:
            return [Finding("VALID.WEAK_CONSENSUS", Severity.WARN,
                            f"Agent consensus weak ({share:.0%} dominant vs floor "
                            f"{THRESHOLDS.min_agent_consensus:.0%}) — conflicted signal.",
                            self.name, 2.0, "V2")]
        return []

    # ── V3: Monte Carlo stability ────────────────────────────────────────────
    def _check_stability(self, ctx: TrustContext) -> list[Finding]:
        if ctx.mc_stability < THRESHOLDS.min_mc_stability:
            return [Finding("VALID.UNSTABLE", Severity.WARN,
                            f"Monte Carlo stability {ctx.mc_stability:.0%} below floor "
                            f"{THRESHOLDS.min_mc_stability:.0%} — direction is noisy.",
                            self.name, 2.0, "V3")]
        return []

    # ── V5: track-record awareness ───────────────────────────────────────────
    def _check_track_record(self, ctx: TrustContext) -> list[Finding]:
        if ctx.historical_accuracy < THRESHOLDS.min_historical_accuracy:
            return [Finding("VALID.LOW_TRACK_RECORD", Severity.WARN,
                            f"System accuracy {ctx.historical_accuracy:.0%} below floor "
                            f"{THRESHOLDS.min_historical_accuracy:.0%} — outputs downgraded.",
                            self.name, 1.0, "V5")]
        return []

    # ── V4: calibration — cap confidence by signal order + absolute ceiling ──
    def _confidence_cap(self, ctx: TrustContext, findings: list[Finding]) -> float:
        order = (ctx.signal_order or "primary").lower()
        order_cap = {
            "primary": THRESHOLDS.cap_primary,
            "secondary": THRESHOLDS.cap_secondary,
            "tertiary": THRESHOLDS.cap_tertiary,
        }.get(order, THRESHOLDS.cap_primary)
        return min(order_cap, THRESHOLDS.cap_absolute)
