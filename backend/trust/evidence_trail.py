"""Stage 5 — evidence trail. trace a published prediction back to its sources.

Builds ON the attribution record (already in the hash-chained ledger, keyed by
simulation_id) — not a parallel schema. For one prediction it answers, tamper-
evidently: which sources backed each vote-moving claim, each source's provenance
class and its reputation at decision time, and whether any claim is unbacked.

An unbacked claim ties to Evidence article E5 (no invented facts): a directional
claim that traces to no source is a potential fabrication and is FLAGGED, not
silently presented as evidence.

KNOWN GAP: the I1–I4 input-trust layer is not built, so provenance classes are a
coarse default (external feeds → untrusted_external; the swarm's own causal text →
model_generated). When I1–I4 lands, provenance comes from its ingestion tagging,
and `input_trust_enforced` flips to true.
"""

from __future__ import annotations

from trust.reputation import SOURCE


def _provenance_class(_source_id: str) -> str:
    # all attribution sources are external feeds; I1-I4 would refine this.
    return "untrusted_external"


async def build_evidence_trail(ledger, store, simulation_id: str) -> dict | None:
    """Assemble the evidence trail for a prediction, or None if no attribution.

    Joinable by simulation_id. `complete` is False when any vote-moving claim has
    no backing source (E5 flag) or there are no claims at all.
    """
    attribution = await ledger.find_attribution(simulation_id)
    if not attribution:
        return None

    # per-source provenance + reputation (decision-time snapshot if recorded).
    by_id: dict = {}
    source_records = []
    for s in attribution.get("sources", []) or []:
        sid = s.get("source_id")
        if not sid:
            continue
        rep = s.get("reputation_at_decision")
        tier = s.get("reputation_tier")
        if rep is None and store is not None:
            rep, tier = await store.effective_with_tier(sid, SOURCE)
            rep = round(rep, 4)
        rec = {
            "source_id": sid,
            "provenance_class": _provenance_class(sid),
            "reputation_at_decision": rep,
            "reputation_tier": tier,
            "weight": s.get("weight"),
        }
        by_id[sid] = rec
        source_records.append(rec)

    # each vote-moving claim, traced to its backing sources; unbacked → E5 flag.
    claims = []
    for c in attribution.get("vote_moving_claims", []) or []:
        backing = [by_id[sid] for sid in (c.get("source_ids") or []) if sid in by_id]
        unbacked = len(backing) == 0
        claims.append({
            "slot": c.get("slot"),
            "claim": c.get("claim"),
            "provenance_class": "model_generated",  # the LLM authored the claim text
            "backed_by": backing,
            "unbacked": unbacked,
            "article": "E5" if unbacked else None,
        })

    complete = bool(claims) and all(not c["unbacked"] for c in claims)
    return {
        "simulation_id": simulation_id,
        "ticker": attribution.get("ticker"),
        "direction": attribution.get("direction"),
        "chain_override": attribution.get("chain_override"),
        "driving_archetypes": attribution.get("driving_archetypes"),
        "claims": claims,
        "sources": source_records,
        "complete": complete,
        # false until the I1-I4 input-trust layer tags provenance at ingestion.
        "input_trust_enforced": False,
    }
