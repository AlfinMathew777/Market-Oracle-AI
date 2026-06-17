"""Trust stack data contracts — the shared vocabulary of the 5-layer trust system.

Everything in `backend/trust/` speaks in these immutable types. They are the
only thing layers, the gateway, and the ledger agree on, which keeps the layers
independent (a layer can be rewritten without touching the others).

Design rules:
  - All types are frozen dataclasses — verdicts are evidence, never mutated.
  - A `Finding` is the atomic unit of "something a layer noticed".
  - A `LayerVerdict` is one layer's full opinion (pass/score/cap/veto + findings).
  - A `TrustCertificate` is the gateway's final, signed, replayable decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum


class Severity(IntEnum):
    """How serious a Finding is. BLOCK is a hard veto on action."""

    INFO = 0   # Note for the audit trail — no effect on the decision.
    WARN = 1   # Quality concern — degrades trust / caps confidence.
    BLOCK = 2  # Veto — the prediction must NOT become an actionable signal.


class Decision(str, Enum):  # noqa: UP042 — matches the project's str-enum convention
    """The gateway's final verdict on a prediction."""

    APPROVE = "APPROVE"                     # Trustworthy — publish as-is.
    APPROVE_DEGRADED = "APPROVE_DEGRADED"   # Publish, but confidence capped / monitor-only.
    BLOCK = "BLOCK"                         # Not actionable — do not publish.


# The five layers, in evaluation order. Layer 1 (agents) runs BEFORE the gateway;
# the gateway orchestrates layers 2-5 over the agents' output.
LAYER_AGENTS = "agents"
LAYER_INPUT = "input"
LAYER_EVIDENCE = "evidence"
LAYER_VALIDATION = "validation"
LAYER_RISK = "risk"
LAYER_AUDIT = "audit"


@dataclass(frozen=True)
class Finding:
    """One observation made by a layer.

    `code` is a stable machine identifier (e.g. "EVID.CATALYST_MISSING") so
    downstream analytics can group failures without parsing prose. `article`
    links the finding to the Constitution article it enforces.
    """

    code: str
    severity: Severity
    message: str
    layer: str
    weight: float = 1.0            # Trust-score deduction weight when WARN/BLOCK.
    article: str | None = None  # Constitution article id this enforces.

    @property
    def is_veto(self) -> bool:
        return self.severity == Severity.BLOCK


@dataclass(frozen=True)
class LayerVerdict:
    """One layer's complete opinion on a prediction.

    A layer never decides whether to publish — it only reports. The gateway
    aggregates verdicts into the final Decision. This keeps each layer a pure,
    independently-testable function of the context.
    """

    layer: str
    passed: bool                                   # False if any BLOCK finding.
    score: float                                   # 0-1 trust contribution of this layer.
    confidence_cap: float = 1.0                    # Max confidence this layer permits.
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0
    error: str | None = None                    # Set when the layer itself failed.

    @property
    def veto(self) -> bool:
        """True if this layer hard-blocks the prediction."""
        return (not self.passed) or any(f.is_veto for f in self.findings)


@dataclass(frozen=True)
class InputProvenance:
    """What the I1-I4 input-trust pipeline recorded at ingestion.

    The InputLayer ENFORCES over this; a missing record (None on the context)
    fails closed — raw, unsanitised input must never reach a published signal.
    """

    sanitized: bool = False                 # I1 — normalization ran before any scan.
    wrapped: bool = False                   # I3 — untrusted text wrapped as data.
    evasion_flags: tuple[str, ...] = field(default_factory=tuple)  # I1 WARN flags.
    instructions_neutralized: int = 0       # I3 telemetry.
    model_generated_cited: bool = False     # I2 veto — own output cited as authority.
    independent_origins: int = 0            # I4 — distinct primary origins.
    single_source: bool = False             # I4 — uncorroborated → confidence cap.
    low_rep_cluster: bool = False           # I4 veto — low-rep/new-source cluster.


@dataclass(frozen=True)
class TrustContext:
    """Normalised, layer-readable view of one prediction.

    The gateway builds this once from the raw prediction dict so that layers
    never reach into messy, source-specific shapes. `raw` retains the original
    for the audit record.
    """

    ticker: str
    direction: str                  # BULLISH / BEARISH / NEUTRAL (normalised upstream-ish).
    confidence: float               # 0-1.
    signal_order: str = "primary"   # primary / secondary / tertiary.
    catalyst: str = ""              # trigger_event text.
    agent_votes: dict = field(default_factory=dict)   # {bull, bear, neut}.
    mc_stability: float = 1.0       # Monte Carlo direction stability 0-1.
    historical_accuracy: float = 1.0  # System hit-rate 0-1 (1.0 = unknown/assume ok).
    judge_result: dict = field(default_factory=dict)
    market_context: dict = field(default_factory=dict)
    data_feeds: dict = field(default_factory=dict)    # {feed: age_seconds}.
    paper_mode: bool = True
    raw: dict = field(default_factory=dict)
    # I1-I4 record from ingestion. None ⇒ sanitization not proven ⇒ fail closed.
    input_provenance: InputProvenance | None = None


@dataclass(frozen=True)
class TrustCertificate:
    """The gateway's final, signed, replayable verdict.

    This object is what every API response should carry. Because it is written
    to the hash-chained ledger, anyone can later re-run the layers on `raw` and
    confirm the same certificate was issued — tamper-evident provenance.
    """

    decision: Decision
    trust_score: int                 # 0-100.
    confidence_in: float
    confidence_out: float            # After all layer caps applied.
    direction_in: str
    direction_out: str
    constitution_version: str
    layer_verdicts: tuple[LayerVerdict, ...] = field(default_factory=tuple)
    findings: tuple[Finding, ...] = field(default_factory=tuple)
    explain: str = ""                # Human-readable "why".
    issued_at: str = ""              # ISO8601 UTC.
    ledger_seq: int | None = None
    ledger_hash: str | None = None

    @property
    def is_actionable(self) -> bool:
        return self.decision in (Decision.APPROVE, Decision.APPROVE_DEGRADED)

    def to_dict(self) -> dict:
        """Flat, JSON-safe dict for API responses and ledger storage."""
        return {
            "decision": self.decision.value,
            "trust_score": self.trust_score,
            "confidence_in": round(self.confidence_in, 4),
            "confidence_out": round(self.confidence_out, 4),
            "direction_in": self.direction_in,
            "direction_out": self.direction_out,
            "constitution_version": self.constitution_version,
            "issued_at": self.issued_at,
            "ledger_seq": self.ledger_seq,
            "ledger_hash": self.ledger_hash,
            "explain": self.explain,
            "findings": [
                {
                    "code": f.code,
                    "severity": f.severity.name,
                    "message": f.message,
                    "layer": f.layer,
                    "article": f.article,
                }
                for f in self.findings
            ],
            "layers": [
                {
                    "layer": v.layer,
                    "passed": v.passed,
                    "score": round(v.score, 4),
                    "confidence_cap": round(v.confidence_cap, 4),
                    "veto": v.veto,
                    "duration_ms": round(v.duration_ms, 2),
                    "error": v.error,
                }
                for v in self.layer_verdicts
            ],
        }
