"""Data-availability audit: can per-archetype analyses run on the ledger?

Blocks or unblocks two ordered analyses (Prediction Masters directive):
per-archetype-vs-median-ensemble and the pairwise agent-agreement matrix.
Both need per-agent (or per-archetype) votes per prediction. This script
measures whether any persisted surface actually contains them.

Read-only, stdlib only, imports nothing from backend/.
"""

import argparse
import json
import sqlite3


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    cur = con.cursor()

    total, non_null = cur.execute(
        "SELECT COUNT(*), SUM(agent_votes IS NOT NULL) FROM simulations"
    ).fetchone()
    lens: dict[int, int] = {}
    per_agent_fields = 0
    for (av,) in cur.execute("SELECT agent_votes FROM simulations WHERE agent_votes IS NOT NULL"):
        try:
            parsed = json.loads(av)
        except (TypeError, ValueError):
            parsed = None
        n = len(parsed) if isinstance(parsed, list) else -1
        lens[n] = lens.get(n, 0) + 1
        if isinstance(parsed, list) and any(
            isinstance(e, dict) and ("persona" in e or "archetype" in e or "agent_id" in e)
            for e in parsed
        ):
            per_agent_fields += 1

    fj_total, fj_with = cur.execute(
        "SELECT COUNT(*), SUM(full_json IS NOT NULL) FROM simulations"
    ).fetchone()
    fj_agent_detail = 0
    fj_keys_seen: set[str] = set()
    for (fj,) in cur.execute("SELECT full_json FROM simulations WHERE full_json IS NOT NULL"):
        try:
            parsed = json.loads(fj)
        except (TypeError, ValueError):
            continue
        fj_keys_seen.update(k for k in parsed if "agent" in k.lower() or "persona" in k.lower())
        consensus = parsed.get("agent_consensus")
        # aggregate counts ({up/down/neutral}) do NOT unblock per-agent analyses
        if isinstance(consensus, list):
            fj_agent_detail += 1

    rp_with = cur.execute(
        "SELECT SUM(agent_consensus IS NOT NULL) FROM reasoning_predictions"
    ).fetchone()[0]

    print(
        json.dumps(
            {
                "simulations_total": total,
                "agent_votes_non_null": non_null,
                "agent_votes_length_histogram": lens,
                "rows_with_per_agent_identity": per_agent_fields,
                "full_json_rows": fj_with,
                "full_json_rows_with_per_agent_detail": fj_agent_detail,
                "full_json_agentish_keys": sorted(fj_keys_seen),
                "reasoning_predictions_with_agent_consensus": rp_with,
                "verdict_per_archetype_analyses": (
                    "UNBLOCKED" if per_agent_fields or fj_agent_detail else "BLOCKED"
                ),
            },
            indent=2,
        )
    )
    con.close()


if __name__ == "__main__":
    main()
