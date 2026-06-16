"""Layer 4 — RISK: controls action.

The Evidence and Validation layers judge the *prediction*. This layer judges
whether the *world is in a state where acting is allowed*, independent of how
good the prediction looks. Human controls and system state win over model
quality every time:

  - R1 Kill switch — if a human has halted signals, nothing is actionable.
  - R4 Neutral — a NEUTRAL prediction is never a tradeable signal.
  - R3 Advice framing — user-facing text must stay probabilistic, never imperative.

This layer is deliberately conservative: it can only ever *reduce* actionability.
It never raises trust.
"""

from __future__ import annotations

import logging
import re

from trust.contracts import Finding, Severity, TrustContext
from trust.layers.base import TrustLayer

logger = logging.getLogger(__name__)

# Imperative advice language forbidden in user-facing reason text (Article R3).
_ADVICE_PATTERNS = (
    re.compile(r"\byou should (buy|sell|invest)\b", re.I),
    re.compile(r"\b(buy|sell) (now|immediately|today)\b", re.I),
    re.compile(r"\bguaranteed\b", re.I),
    re.compile(r"\bwe recommend (buying|selling)\b", re.I),
)


class RiskLayer(TrustLayer):
    name = "risk"

    async def _check(self, ctx: TrustContext) -> list[Finding]:
        findings: list[Finding] = []
        findings += self._check_kill_switch(ctx)
        findings += self._check_neutral(ctx)
        findings += self._check_advice_framing(ctx)
        return findings

    # ── R1: kill switch supremacy ────────────────────────────────────────────
    def _check_kill_switch(self, ctx: TrustContext) -> list[Finding]:
        try:
            from system_state import is_signals_enabled
            enabled = is_signals_enabled()
        except Exception as e:  # noqa: BLE001
            # Fail-closed: if we cannot confirm signals are enabled, assume halted.
            logger.warning("kill-switch state unreadable, assuming HALTED: %s", e)
            return [Finding("RISK.KILL_SWITCH_UNKNOWN", Severity.BLOCK,
                            "Kill-switch state could not be read — blocking (fail-closed).",
                            self.name, 1.0, "R1")]
        if not enabled:
            return [Finding("RISK.KILL_SWITCH_ACTIVE", Severity.BLOCK,
                            "Kill switch is ACTIVE — all signals halted by operator.",
                            self.name, 1.0, "R1")]
        return []

    # ── R4: neutral is not actionable ────────────────────────────────────────
    def _check_neutral(self, ctx: TrustContext) -> list[Finding]:
        if ctx.direction.upper() == "NEUTRAL":
            return [Finding("RISK.NEUTRAL", Severity.WARN,
                            "NEUTRAL prediction — logged but not a tradeable signal.",
                            self.name, 1.0, "R4")]
        return []

    # ── R3: no advice framing ────────────────────────────────────────────────
    def _check_advice_framing(self, ctx: TrustContext) -> list[Finding]:
        text_fields = [ctx.catalyst]
        text_fields += [str(v) for v in (ctx.judge_result or {}).values()]
        text_fields.append(str(ctx.raw.get("reason", "")))
        blob = " ".join(text_fields)
        for pat in _ADVICE_PATTERNS:
            if pat.search(blob):
                return [Finding("RISK.ADVICE_LANGUAGE", Severity.WARN,
                                f"User-facing text uses advice language matching /{pat.pattern}/ "
                                "— must stay probabilistic (AFSL).",
                                self.name, 1.0, "R3")]
        return []
