"""I2 (no self-trust / provenance) + I4 (corroborated aggregate).

I2 is LOAD-BEARING. provenance is assigned by ORIGIN, never by content — so the
tag holds even when I1 misses a homoglyph. model_generated content is never
authoritative evidence; an agent cannot bootstrap authority from its own output.

I4 weights a claim by INDEPENDENT corroboration, where independent = distinct
PRIMARY ORIGIN, not distinct domain. honest single source → publish, capped,
labeled uncorroborated (a real scoop and a planted lie look identical at minute
one — we do not delete scoops to stop fakes). veto is reserved for the low-rep /
new-source CLUSTER pattern only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# RESEARCH-TODO (#1): real primary-origin / independence detection. v1 collapses
# by host with a wire-service hint list — domain-count is KNOWN-WEAK and must
# never be presented as independence.
_WIRE_SERVICES = ("reuters", "ap", "bloomberg", "afp", "aap")


class TrustClass(str, Enum):  # noqa: UP042 — matches the project's str-enum convention
    TRUSTED = "trusted_source"
    UNTRUSTED = "untrusted_external"
    MODEL = "model_generated"


def classify_provenance(origin_kind: str) -> TrustClass:
    """Origin → trust class. default is untrusted; never inferred from content."""
    if origin_kind == "model":
        return TrustClass.MODEL
    if origin_kind == "trusted":
        return TrustClass.TRUSTED
    return TrustClass.UNTRUSTED


@dataclass(frozen=True)
class Corroboration:
    independent_origins: int
    single_source: bool
    low_rep_cluster: bool  # veto case: cluster of low-rep sources, no trusted backing


def _primary_origin(source_id: str) -> str:
    # KNOWN-WEAK: collapse syndication toward one origin by host + wire hint.
    sid = (source_id or "").lower().strip()
    host = sid.split("/")[0]
    for wire in _WIRE_SERVICES:
        if wire in host:
            return wire  # 50 outlets reprinting one wire → one origin
    return host or sid


def assess_corroboration(
    sources: list[dict], *, min_reputation: float, low_rep_cluster_min: int,
) -> Corroboration:
    """Independence + the low-rep-cluster veto signal from a claim's sources.

    sources: dicts with source_id, optional reputation, optional provenance_class.
    """
    origins = {_primary_origin(s.get("source_id", "")) for s in sources if s.get("source_id")}
    n = len(origins)

    low_rep = [s for s in sources if float(s.get("reputation") or 0.0) < min_reputation]
    has_trusted = any(s.get("provenance_class") == TrustClass.TRUSTED.value for s in sources)
    # poisoning pattern: every backing source is low-rep and none is trusted.
    cluster = (
        not has_trusted
        and len(sources) >= low_rep_cluster_min
        and len(low_rep) == len(sources)
    )
    return Corroboration(independent_origins=n, single_source=(n <= 1), low_rep_cluster=cluster)
