"""Layer 1.5 — INPUT: enforces the I1-I4 input-trust record.

The work (normalize / tag / wrap / corroborate) runs at ingestion; this layer
ENFORCES that it ran and that no unhandled evasion reaches a published signal.

Fail-closed: a missing provenance record is a BLOCK — raw input is never trusted
by default. I2/I3 are the load-bearing wall — a missing tag or unwrapped untrusted
text is a hard veto regardless of what the I1 normalizer caught. I4 caps an honest
single source; it vetoes only the low-reputation cluster.
"""

from __future__ import annotations

from trust.constitution import THRESHOLDS
from trust.contracts import Finding, Severity, TrustContext
from trust.layers.base import TrustLayer


class InputLayer(TrustLayer):
    name = "input"

    async def _check(self, ctx: TrustContext) -> list[Finding]:
        ip = ctx.input_provenance

        # fail-closed: no record ⇒ sanitization not proven.
        if ip is None:
            if THRESHOLDS.require_sanitized_input:
                return [Finding(
                    "INPUT.NOT_SANITIZED", Severity.BLOCK,
                    "No input-trust record — sanitization not proven; blocking (fail-closed).",
                    self.name, 1.0, "I1")]
            return []

        findings: list[Finding] = []
        if not ip.sanitized:
            findings.append(Finding("INPUT.RAW_UNSANITIZED", Severity.BLOCK,
                            "Input was not normalized before use (I1).", self.name, 1.0, "I1"))
        if ip.model_generated_cited:
            findings.append(Finding("INPUT.SELF_TRUST", Severity.BLOCK,
                            "model_generated content cited as authoritative evidence (I2).",
                            self.name, 1.0, "I2"))
        if not ip.wrapped:
            findings.append(Finding("INPUT.UNWRAPPED", Severity.BLOCK,
                            "Untrusted external text not wrapped as data (I3).", self.name, 1.0, "I3"))

        # I4 — low-rep cluster is the ONLY veto; an honest single source is capped.
        if ip.low_rep_cluster:
            findings.append(Finding("INPUT.LOW_REP_CLUSTER", Severity.BLOCK,
                            "Claim backed only by a low-reputation/new-source cluster (I4).",
                            self.name, 1.0, "I4"))
        elif ip.single_source:
            findings.append(Finding("INPUT.UNCORROBORATED", Severity.WARN,
                            "Single-source claim — published but confidence capped (I4).",
                            self.name, 1.0, "I4"))

        # I1 evasion flags degrade trust; the wall (I2/I3) carries the real veto.
        for flag in ip.evasion_flags:
            findings.append(Finding(f"INPUT.EVASION_{flag.upper()}", Severity.WARN,
                            f"Normalization flagged '{flag}' in untrusted input (I1).",
                            self.name, 0.5, "I1"))
        return findings

    def _confidence_cap(self, ctx: TrustContext, findings: list[Finding]) -> float:
        ip = ctx.input_provenance
        # uncorroborated single source still publishes, but capped (I4).
        if ip is not None and ip.single_source and not ip.low_rep_cluster:
            return THRESHOLDS.cap_uncorroborated
        return 1.0
