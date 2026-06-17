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
