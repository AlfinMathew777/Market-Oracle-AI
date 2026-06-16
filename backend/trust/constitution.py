"""The Trust Constitution — the written rules every prediction is checked against.

Modelled on Anthropic's Constitutional AI: instead of trust being an emergent,
unexplainable property of the model, it is an explicit, versioned contract. Each
Article states a rule a trustworthy prediction MUST satisfy, names the layer that
enforces it, and carries the severity of a violation.

Layers reference these articles by id when they raise Findings, so every block or
warning traces back to a human-readable rule — that is what makes the system
auditable at the "why" level.

VERSIONING: bump CONSTITUTION_VERSION on any change to thresholds or articles.
The version is stamped into every TrustCertificate, so a decision can always be
replayed against the exact ruleset that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass

from trust.contracts import Severity

CONSTITUTION_VERSION = "1.0.0"


@dataclass(frozen=True)
class Article:
    id: str
    layer: str
    title: str
    rule: str
    severity: Severity


# ── Hard numeric thresholds (single source of truth, mirrors signal-quality rules) ──
@dataclass(frozen=True)
class Thresholds:
    # Evidence layer
    max_empty_causal_slots: int = 2          # > this ⇒ chain is hollow.
    max_feed_age_seconds: int = 1800         # 30 min — staler critical feed blocks.

    # Validation layer
    min_confidence_actionable: float = 0.55  # Below ⇒ not a BUY/SELL.
    min_confidence_monitor: float = 0.40     # Below ⇒ HOLD, not even WAIT.
    min_mc_stability: float = 0.30           # Monte Carlo direction stability floor.
    min_agent_consensus: float = 0.55        # Dominant-side vote share.
    min_historical_accuracy: float = 0.40    # System hit-rate floor.

    # Confidence caps by signal order (never exceeded)
    cap_primary: float = 0.75
    cap_secondary: float = 0.55
    cap_tertiary: float = 0.35
    cap_absolute: float = 0.85               # Hard ceiling. Never 100%.

    # Gateway decision
    min_trust_score_actionable: int = 60     # Below ⇒ BLOCK regardless of confidence.
    degraded_trust_score: int = 80           # Below ⇒ APPROVE_DEGRADED at best.


THRESHOLDS = Thresholds()


# ── The Articles ────────────────────────────────────────────────────────────────
ARTICLES: tuple[Article, ...] = (
    # Layer 2 — Evidence (truth)
    Article(
        "E1", "evidence", "Grounded catalyst",
        "Every directional signal must cite a specific, real catalyst. Generic "
        "phrases ('general market conditions', 'no direct impact') are not catalysts.",
        Severity.BLOCK,
    ),
    Article(
        "E2", "evidence", "Substantiated causal chain",
        "The causal chain must not be hollow. More than the allowed number of "
        "empty/fallback slots indicates a synthesis timeout, not analysis.",
        Severity.WARN,
    ),
    Article(
        "E3", "evidence", "Geographic truth",
        "Supply-chain reasoning must respect physical fact (Australian iron ore "
        "transits Lombok/Makassar, NOT Malacca). Geographic errors void the signal.",
        Severity.BLOCK,
    ),
    Article(
        "E4", "evidence", "Fresh data",
        "Predictions must be grounded in fresh market data. A stale critical feed "
        "means the model is reasoning over fiction.",
        Severity.BLOCK,
    ),
    Article(
        "E5", "evidence", "No invented facts",
        "The model may only reference data present in its inputs. Invented prices, "
        "events, or figures void the signal.",
        Severity.BLOCK,
    ),

    # Layer 3 — Validation (quality)
    Article(
        "V1", "validation", "Confidence floor",
        "An actionable signal requires confidence at or above the actionable floor; "
        "below the monitor floor it is not even worth watching.",
        Severity.BLOCK,
    ),
    Article(
        "V2", "validation", "Agent consensus",
        "The dominant side must command a real majority of agent votes. A near-tie "
        "is a conflicted, untradeable signal.",
        Severity.WARN,
    ),
    Article(
        "V3", "validation", "Monte Carlo stability",
        "The predicted direction must survive Monte Carlo perturbation. An unstable "
        "direction is noise.",
        Severity.WARN,
    ),
    Article(
        "V4", "validation", "Calibrated confidence",
        "Confidence must respect the per-order caps and the absolute 85% ceiling. "
        "No prediction is ever 100% certain.",
        Severity.WARN,
    ),
    Article(
        "V5", "validation", "Track-record awareness",
        "When the system's historical accuracy is below the floor, its outputs are "
        "downgraded until accuracy recovers.",
        Severity.WARN,
    ),

    # Layer 4 — Risk (action control)
    Article(
        "R1", "risk", "Kill switch supremacy",
        "When the kill switch is active, no signal is actionable, regardless of "
        "quality. Human override always wins.",
        Severity.BLOCK,
    ),
    Article(
        "R2", "risk", "Fail closed",
        "If any trust layer cannot complete its check, the prediction is blocked. "
        "Absence of a green light is a red light.",
        Severity.BLOCK,
    ),
    Article(
        "R3", "risk", "No advice framing",
        "Outputs are probabilistic predictions, never financial advice. Imperative "
        "language ('buy', 'sell now') is forbidden in user-facing text.",
        Severity.WARN,
    ),
    Article(
        "R4", "risk", "Neutral is not actionable",
        "A NEUTRAL prediction is logged but never published as a tradeable signal — "
        "there is nothing to act on.",
        Severity.WARN,
    ),

    # Layer 5 — Audit (proof)
    Article(
        "A1", "audit", "Tamper-evident record",
        "Every decision is written to the hash-chained ledger before it is acted on. "
        "A decision that cannot be recorded cannot be trusted.",
        Severity.BLOCK,
    ),
    Article(
        "A2", "audit", "Replayability",
        "Every certificate carries the constitution version and full inputs so the "
        "decision can be independently re-derived.",
        Severity.INFO,
    ),
)

_BY_ID = {a.id: a for a in ARTICLES}


def article(article_id: str) -> Article:
    """Look up an Article by id (raises KeyError if unknown — fail loud)."""
    return _BY_ID[article_id]


def articles_for(layer: str) -> tuple[Article, ...]:
    return tuple(a for a in ARTICLES if a.layer == layer)
