"""Append one entry to the trials register (docs/trials/register.jsonl).

The register is the multiplicity ledger demanded by the Deflated-Sharpe
discipline (docs/extraction-table.md): every configuration, prompt, or
threshold variant EVALUATED gets an entry — kept or discarded. An experiment
that isn't registered cannot later be honestly counted, so append BEFORE
running the experiment and update `result` by appending a follow-up entry
(never by editing — the chain makes edits detectable).

Entries are hash-chained: entry_hash = sha256(prev_hash + canonical entry
JSON without the hash fields). Genesis prev_hash is 64 zeros. The verifier
(`scripts/verify/verify_trials_register.py`) re-walks the chain independently.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64
_HASH_FIELDS = ("prev_hash", "entry_hash")


def canonical(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k not in _HASH_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(entry)).encode("utf-8")).hexdigest()


def append_entry(register: Path, entry: dict) -> dict:
    lines = register.read_text(encoding="utf-8").splitlines() if register.exists() else []
    prev = json.loads(lines[-1]) if lines else None
    entry["seq"] = (prev["seq"] + 1) if prev else 1
    entry["prev_hash"] = prev["entry_hash"] if prev else GENESIS
    entry["entry_hash"] = chain_hash(entry["prev_hash"], entry)
    register.parent.mkdir(parents=True, exist_ok=True)
    with register.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="docs/trials/register.jsonl")
    ap.add_argument("--description", required=True)
    ap.add_argument("--config", required=True, help="config content/spec string; stored as sha256")
    ap.add_argument("--metric", required=True, help="what is being measured")
    ap.add_argument("--result", default="pending", help="outcome; 'pending' until known")
    ap.add_argument("--source", choices=("live", "backfilled"), default="live")
    ap.add_argument("--git-ref", default=None, help="introducing commit for backfilled entries")
    args = ap.parse_args()

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": args.source,
        "git_ref": args.git_ref,
        "config_hash": hashlib.sha256(args.config.encode("utf-8")).hexdigest(),
        "config_spec": args.config,
        "description": args.description,
        "metric": args.metric,
        "result": args.result,
    }
    written = append_entry(Path(args.register), entry)
    print(json.dumps(written, indent=2))


if __name__ == "__main__":
    main()
