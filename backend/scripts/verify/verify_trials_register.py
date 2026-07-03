"""Verify the trials register (docs/trials/register.jsonl) — Stage 2b style.

Independent re-walk of the hash chain; imports nothing from backend/ and
deliberately re-implements the hashing spec (drift = alarm):

  entry_hash = sha256(prev_hash + canonical(entry))
  canonical  = JSON of the entry without prev_hash/entry_hash,
               sorted keys, separators (",", ":"), UTF-8, ensure_ascii=False
  genesis prev_hash = 64 zeros

Checks: parseable JSONL; required fields; seq starts at 1 and increments by
1; ts is ISO-8601 and non-decreasing; source in {live, backfilled};
backfilled entries carry a git_ref; config_hash equals sha256(config_spec);
chain links and hashes all verify.

Exit codes: 0 clean, 1 violation (one line per finding), 2 bad usage.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

GENESIS = "0" * 64
REQUIRED = (
    "seq", "ts", "source", "git_ref", "config_hash", "config_spec",
    "description", "metric", "result", "prev_hash", "entry_hash",
)


def canonical(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash")}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--register", default="docs/trials/register.jsonl")
    args = ap.parse_args()

    path = Path(args.register)
    if not path.exists():
        print(f"register missing: {path}")
        return 1

    findings: list[str] = []
    prev_hash = GENESIS
    prev_seq = 0
    prev_ts = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError as exc:
            findings.append(f"line {lineno}: unparseable JSON ({exc})")
            break
        missing = [f for f in REQUIRED if f not in entry]
        if missing:
            findings.append(f"line {lineno}: missing fields {missing}")
            continue
        if entry["seq"] != prev_seq + 1:
            findings.append(f"line {lineno}: seq {entry['seq']} != {prev_seq + 1}")
        try:
            ts = datetime.fromisoformat(entry["ts"])
            if prev_ts is not None and ts < prev_ts:
                findings.append(f"line {lineno}: ts decreases ({entry['ts']})")
            prev_ts = ts
        except ValueError:
            findings.append(f"line {lineno}: bad ts {entry['ts']!r}")
        if entry["source"] not in ("live", "backfilled"):
            findings.append(f"line {lineno}: bad source {entry['source']!r}")
        if entry["source"] == "backfilled" and not entry["git_ref"]:
            findings.append(f"line {lineno}: backfilled entry without git_ref")
        want_cfg = hashlib.sha256(entry["config_spec"].encode("utf-8")).hexdigest()
        if entry["config_hash"] != want_cfg:
            findings.append(f"line {lineno}: config_hash mismatch")
        if entry["prev_hash"] != prev_hash:
            findings.append(f"line {lineno}: chain break (prev_hash mismatch)")
        want = hashlib.sha256((entry["prev_hash"] + canonical(entry)).encode("utf-8")).hexdigest()
        if entry["entry_hash"] != want:
            findings.append(f"line {lineno}: entry_hash mismatch (tampered or mis-appended)")
        prev_hash = entry["entry_hash"]
        prev_seq = entry["seq"]

    if findings:
        print("\n".join(findings))
        return 1
    print(f"trials register OK: {prev_seq} entries, chain intact, head {prev_hash[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
