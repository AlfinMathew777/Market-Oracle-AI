"""Layer 2 — EVIDENCE: checks truth.

This layer asks one question: *is the prediction grounded in reality?* It does
NOT judge whether the trade is good (that is Validation) — only whether the
reasoning rests on real, fresh, geographically-correct facts and a concrete
catalyst.

It is an ADAPTER. The truth-checking logic already exists in the project's
validators; this layer composes them and translates their outputs into Findings
tied to Constitution articles E1-E5. Each validator is called defensively so a
missing/renamed dependency degrades to a WARN rather than crashing the gateway.
"""

from __future__ import annotations

import logging

from trust.constitution import THRESHOLDS
from trust.contracts import Finding, Severity, TrustContext
from trust.layers.base import TrustLayer

logger = logging.getLogger(__name__)

# Geographic facts that, if violated, void a supply-chain signal (Article E3).
_GEO_FORBIDDEN = (
    ("iron ore", "malacca"),    # AU iron ore does NOT transit Malacca.
    ("iron ore", "suez"),       # ...nor Suez.
)


class EvidenceLayer(TrustLayer):
    name = "evidence"

    async def _check(self, ctx: TrustContext) -> list[Finding]:
        findings: list[Finding] = []
        findings += self._check_catalyst(ctx)
        findings += self._check_causal_chain(ctx)
        findings += self._check_geography(ctx)
        findings += self._check_data_freshness(ctx)
        return findings

    # ── E1: grounded catalyst ────────────────────────────────────────────────
    def _check_catalyst(self, ctx: TrustContext) -> list[Finding]:
        # NEUTRAL signals don't require a catalyst — nothing is being claimed.
        if ctx.direction.upper() == "NEUTRAL":
            return []
        catalyst = (ctx.catalyst or "").strip()
        if not catalyst:
            return [Finding("EVID.CATALYST_MISSING", Severity.BLOCK,
                            "Directional signal has no catalyst.", self.name, 1.0, "E1")]
        try:
            from services.catalyst_validator import validate_catalyst
            is_valid, reason = validate_catalyst(catalyst)
            if not is_valid:
                return [Finding("EVID.CATALYST_INVALID", Severity.BLOCK,
                                f"Catalyst rejected: {reason}", self.name, 1.0, "E1")]
        except Exception as e:  # noqa: BLE001
            logger.warning("catalyst_validator unavailable, degrading to WARN: %s", e)
            return [Finding("EVID.CATALYST_UNCHECKED", Severity.WARN,
                            "Catalyst could not be validated (validator unavailable).",
                            self.name, 1.0, "E1")]
        return []

    # ── E2: substantiated causal chain ───────────────────────────────────────
    def _check_causal_chain(self, ctx: TrustContext) -> list[Finding]:
        if not ctx.judge_result:
            return []
        try:
            from services.causal_chain_validator import validate_causal_chain
            result = validate_causal_chain(ctx.judge_result)
        except Exception as e:  # noqa: BLE001
            logger.warning("causal_chain_validator unavailable: %s", e)
            return []
        empty = int(result.get("empty_count", 0))
        quality = result.get("chain_quality", "ADEQUATE")
        if empty > THRESHOLDS.max_empty_causal_slots or quality == "EMPTY":
            slots = ", ".join(result.get("empty_slots", [])) or "multiple"
            return [Finding("EVID.CHAIN_HOLLOW", Severity.WARN,
                            f"Causal chain is hollow ({empty} empty slots: {slots}).",
                            self.name, 2.0, "E2")]
        if quality == "SPARSE":
            return [Finding("EVID.CHAIN_SPARSE", Severity.WARN,
                            "Causal chain is sparse — some slots are fallback text.",
                            self.name, 1.0, "E2")]
        return []

    # ── E3: geographic truth ─────────────────────────────────────────────────
    def _check_geography(self, ctx: TrustContext) -> list[Finding]:
        haystack = " ".join(str(v) for v in ctx.judge_result.values()).lower()
        haystack += " " + (ctx.catalyst or "").lower()
        for commodity, wrong_route in _GEO_FORBIDDEN:
            if commodity in haystack and wrong_route in haystack:
                return [Finding("EVID.GEO_ERROR", Severity.BLOCK,
                                f"Geographic error: '{commodity}' linked to '{wrong_route}' "
                                "(AU iron ore transits Lombok/Makassar).",
                                self.name, 1.0, "E3")]
        return []

    # ── E4: fresh data ───────────────────────────────────────────────────────
    def _check_data_freshness(self, ctx: TrustContext) -> list[Finding]:
        findings: list[Finding] = []
        for feed, age in (ctx.data_feeds or {}).items():
            try:
                age_s = float(age)
            except (TypeError, ValueError):
                continue
            if age_s > THRESHOLDS.max_feed_age_seconds:
                findings.append(Finding(
                    "EVID.FEED_STALE", Severity.BLOCK,
                    f"Feed '{feed}' is stale ({int(age_s)}s > "
                    f"{THRESHOLDS.max_feed_age_seconds}s).",
                    self.name, 1.0, "E4"))
        return findings
