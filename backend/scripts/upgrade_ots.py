"""Upgrade a pending OpenTimestamps proof to a Bitcoin-attested one.

Companion to anchor_ots.py (same Windows rationale — drives the library's
calendar path directly). Queries each pending attestation's calendar for the
completed timestamp and merges it; rewrites the .ots in place only when new
attestations arrived.

Usage: python backend/scripts/upgrade_ots.py <file>.ots
Exit: 0 = proof now carries a Bitcoin attestation; 3 = still pending
(try again later); 1 = error.
"""

import argparse
import sys

from opentimestamps.calendar import RemoteCalendar
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.serialize import (
    BytesDeserializationContext,
    BytesSerializationContext,
    StreamDeserializationContext,
    StreamSerializationContext,
)
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp


def _bitcoin_heights(ts: Timestamp) -> list[int]:
    return [
        a.height for _, a in ts.all_attestations()
        if isinstance(a, BitcoinBlockHeaderAttestation)
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path")
    args = ap.parse_args()

    with open(args.path, "rb") as fd:
        detached = DetachedTimestampFile.deserialize(StreamDeserializationContext(fd))
    ts = detached.timestamp

    if _bitcoin_heights(ts):
        print(f"already Bitcoin-attested: block(s) {_bitcoin_heights(ts)}")
        return 0

    upgraded = False
    for msg, attestation in list(ts.all_attestations()):
        if not isinstance(attestation, PendingAttestation):
            continue
        uri = attestation.uri.decode("utf-8", "replace") if isinstance(attestation.uri, bytes) else attestation.uri
        try:
            upgraded_ts = RemoteCalendar(uri).get_timestamp(msg)
        except Exception as exc:  # noqa: BLE001 — calendar may not have aggregated yet
            print(f"calendar {uri}: not ready ({exc})")
            continue
        # graft the calendar's completed tree onto the node holding this attestation
        for node in _nodes_with_msg(ts, msg):
            node.merge(upgraded_ts)
            upgraded = True
        print(f"calendar {uri}: upgrade merged")

    if upgraded:
        with open(args.path, "wb") as fd:
            detached.serialize(StreamSerializationContext(fd))
    heights = _bitcoin_heights(ts)
    if heights:
        print(f"Bitcoin attestation present: block(s) {sorted(set(heights))} — proof rewritten")
        return 0
    print("still pending — calendars have not aggregated to Bitcoin yet; retry later")
    return 3


def _nodes_with_msg(ts: Timestamp, msg: bytes) -> list[Timestamp]:
    found = []
    stack = [ts]
    while stack:
        node = stack.pop()
        if node.msg == msg:
            found.append(node)
        stack.extend(node.ops.values())
    return found


if __name__ == "__main__":
    sys.exit(main())
