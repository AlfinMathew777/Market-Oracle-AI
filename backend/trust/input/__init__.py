"""Input-trust layer (I1–I4) — the work side, run at ingestion BEFORE agents.

Pipeline for one piece of untrusted external text:
  I1 normalize  →  I2 tag by origin  →  I3 neutralize + wrap as data

`sanitize_external_text` is the single entry the swarm calls before any external
text reaches an agent. The InputLayer (gateway) later ENFORCES that this ran and
that no evasion went unhandled — fail-closed if the record is missing.

LOAD-BEARING INVARIANT: even if I1 misses a homoglyph, the output is STILL tagged
untrusted (I2) and wrapped as data (I3). A missed glyph can never reach reasoning
as trusted — the tag+wrap do not depend on the glyph. The harness proves this.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trust.input.normalize import normalize_text
from trust.input.provenance import (
    Corroboration,
    TrustClass,
    assess_corroboration,
    classify_provenance,
)
from trust.input.separation import neutralize_instructions, wrap_as_data

__all__ = [
    "SanitizedInput", "sanitize_external_text", "normalize_text",
    "TrustClass", "Corroboration", "assess_corroboration", "classify_provenance",
    "neutralize_instructions", "wrap_as_data",
    "FieldSanitization", "sanitize_fields", "build_input_provenance",
]


@dataclass(frozen=True)
class SanitizedInput:
    """Result of running untrusted text through I1→I2→I3. Immutable evidence."""

    original: str
    normalized: str
    wrapped: str                  # delimiter-wrapped, safe to put in a prompt
    provenance_class: str         # untrusted_external by default (by origin)
    normalization_flags: tuple[str, ...] = field(default_factory=tuple)
    instructions_neutralized: int = 0

    @property
    def is_untrusted(self) -> bool:
        return self.provenance_class == TrustClass.UNTRUSTED.value


@dataclass(frozen=True)
class FieldSanitization:
    """Result of sanitizing a set of named untrusted fields. Every non-empty field
    is wrapped — `wrapped` maps field name → ready-for-prompt delimited data."""

    wrapped: dict = field(default_factory=dict)
    evasion_flags: tuple[str, ...] = field(default_factory=tuple)
    instructions_neutralized: int = 0
    fields_covered: int = 0


def sanitize_fields(fields: dict) -> FieldSanitization:
    """Sanitize+wrap every non-empty untrusted field. None/empty fields are skipped.

    Guarantees: each returned value is delimiter-wrapped data — no raw untrusted
    field text passes through. The caller decides whether ALL untrusted paths were
    routed here (FULL) or some bypassed (PARTIAL).
    """
    wrapped: dict = {}
    flags: set = set()
    neutralized = 0
    for name, raw in (fields or {}).items():
        if raw is None or str(raw).strip() == "":
            continue
        s = sanitize_external_text(str(raw))
        wrapped[name] = s.wrapped
        flags.update(s.normalization_flags)
        neutralized += s.instructions_neutralized
    return FieldSanitization(wrapped, tuple(sorted(flags)), neutralized, len(wrapped))


def build_input_provenance(
    *, field_san: FieldSanitization, sources: list, fully_covered: bool,
    model_cited: bool = False,
) -> dict:
    """Assemble the I1-I4 provenance record from field sanitization + corroboration.

    wrapped_status never overclaims: NONE if nothing wrapped, FULL only when the
    caller asserts every untrusted path was routed through sanitize_fields, else
    PARTIAL (which the gateway caps).
    """
    from trust.constitution import THRESHOLDS
    from trust.contracts import WRAP_FULL, WRAP_NONE, WRAP_PARTIAL

    corr = assess_corroboration(
        sources or [], min_reputation=THRESHOLDS.min_source_reputation,
        low_rep_cluster_min=THRESHOLDS.low_rep_cluster_min,
    )
    if field_san.fields_covered == 0:
        status = WRAP_NONE
    elif fully_covered:
        status = WRAP_FULL
    else:
        status = WRAP_PARTIAL
    return {
        "sanitized": True,
        "wrapped_status": status,
        "evasion_flags": list(field_san.evasion_flags),
        "instructions_neutralized": field_san.instructions_neutralized,
        "model_generated_cited": model_cited,
        "independent_origins": corr.independent_origins,
        "single_source": corr.single_source,
        "low_rep_cluster": corr.low_rep_cluster,
    }


def sanitize_external_text(text: str | None, *, origin_kind: str = "untrusted") -> SanitizedInput:
    """Normalize, tag by origin, neutralize instructions, and wrap as data.

    This is the only sanctioned path for external text into a prompt. The tag and
    the wrap hold regardless of what the normalizer caught — that is the wall.
    """
    normalized, flags = normalize_text(text)
    pclass = classify_provenance(origin_kind)
    neutralized, n = neutralize_instructions(normalized)
    wrapped = wrap_as_data(neutralized)
    return SanitizedInput(
        original=text or "",
        normalized=normalized,
        wrapped=wrapped,
        provenance_class=pclass.value,
        normalization_flags=tuple(flags),
        instructions_neutralized=n,
    )
