"""Verify a trials-register OTS anchor end-to-end (amendment 1 machinery).

Chain of custody checked, hostile-auditor style:
  1. Recompute the register hash chain from raw JSONL (hashing spec
     duplicated on purpose — see verify_trials_register.py) and confirm the
     head-attestation file's `head_entry_hash` and `entries` match the
     recomputed chain at that seq (the head hash commits to every entry).
  2. Confirm the .ots proof's embedded file digest equals sha256 of the
     head-attestation file bytes.
  3. Walk the proof's attestations and report Bitcoin block heights and/or
     pending calendars.

Honest scope limit: step 3 trusts the proof's internal Merkle path as parsed
by the opentimestamps library; confirming the committed merkle root against
the actual Bitcoin block header requires a Bitcoin node or explorer
(`ots verify` elsewhere, or the 2c anchoring page). This script proves the
LOCAL chain of custody: register -> head file -> stamped digest -> claimed
block heights.

Exit: 0 = custody chain verifies (Bitcoin-attested); 3 = verifies but still
calendar-pending; 1 = any custody break.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.serialize import StreamDeserializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

GENESIS = "0" * 64


def _canonical(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k not in ("prev_hash", "entry_hash")}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def recompute_head(register: Path, upto_seq: int) -> str:
    prev = GENESIS
    seq_seen = 0
    for line in register.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        prev = hashlib.sha256((prev + _canonical(entry)).encode("utf-8")).hexdigest()
        seq_seen = entry["seq"]
        if seq_seen == upto_seq:
            return prev
    raise ValueError(f"register has only {seq_seen} entries; head file claims {upto_seq}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("head_file", help="anchors/head-seqN.txt")
    ap.add_argument("--register", default="docs/trials/register.jsonl")
    args = ap.parse_args()

    head_path = Path(args.head_file)
    meta = dict(
        line.split(": ", 1) for line in head_path.read_text(encoding="utf-8").splitlines()
        if ": " in line
    )
    claimed_seq = int(meta["entries"])
    claimed_head = meta["head_entry_hash"].strip()

    # 1. head file vs recomputed register chain
    try:
        recomputed = recompute_head(Path(args.register), claimed_seq)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    if recomputed != claimed_head:
        print(f"FAIL: recomputed chain head {recomputed} != head-file claim {claimed_head}")
        return 1
    print(f"ok: register chain at seq {claimed_seq} == head-file hash {claimed_head[:16]}…")

    # 2. .ots embedded digest vs head-file bytes
    ots_path = Path(str(head_path) + ".ots")
    with ots_path.open("rb") as fd:
        detached = DetachedTimestampFile.deserialize(StreamDeserializationContext(fd))
    actual_digest = hashlib.sha256(head_path.read_bytes()).digest()
    if detached.file_digest != actual_digest:
        print("FAIL: .ots file digest does not match head-attestation file bytes")
        return 1
    print(f"ok: .ots digest matches head file (sha256 {actual_digest.hex()[:16]}…)")

    # 3. attestations
    heights = sorted({
        a.height for _, a in detached.timestamp.all_attestations()
        if isinstance(a, BitcoinBlockHeaderAttestation)
    })
    pending = sorted({
        (a.uri.decode("utf-8", "replace") if isinstance(a.uri, bytes) else a.uri)
        for _, a in detached.timestamp.all_attestations()
        if isinstance(a, PendingAttestation)
    })
    if heights:
        print(f"ok: Bitcoin block attestation(s): {heights} "
              f"(block-header confirmation via a node/explorer is out of scope here)")
        return 0
    if pending:
        print(f"pending: calendar attestations only ({pending}) — run upgrade_ots.py later")
        return 3
    print("FAIL: proof carries no attestations at all")
    return 1


if __name__ == "__main__":
    sys.exit(main())
