"""OpenTimestamps-stamp a file (trials-register anchoring, amendment 1).

The stock `ots` CLI is unusable on Windows (python-bitcoinlib's ctypes
OpenSSL 1.x load fails), so this drives the `opentimestamps` library
directly — the stamping path needs only the calendar HTTP API, none of the
Bitcoin-RPC machinery that breaks. Mirrors `otsclient.cmds.create_timestamp`:
sha256 the file, append a random 16-byte privacy nonce, sha256 again, submit
to independent calendar servers, serialize a detached `.ots` proof.

The fresh proof contains PENDING calendar attestations; Bitcoin attestation
lands after aggregation (~hours). Upgrade later (any machine, any OS):
`ots upgrade <file>.ots` — or re-fetch from the calendars with the URL in
the pending attestation.

Usage: python backend/scripts/anchor_ots.py <file> [--out <file>.ots]
Exit: 0 = proof written with >=1 calendar attestation; 1 = all calendars failed.
"""

import argparse
import os
import sys

from opentimestamps.calendar import RemoteCalendar
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import StreamSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

CALENDARS = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    with open(args.path, "rb") as fd:
        detached = DetachedTimestampFile.from_fd(OpSHA256(), fd)

    # privacy nonce, exactly as otsclient does — calendars see a blinded digest
    nonced = detached.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())

    successes = 0
    for url in CALENDARS:
        try:
            nonced.merge(RemoteCalendar(url).submit(nonced.msg, timeout=20))
            successes += 1
            print(f"anchored via {url}")
        except Exception as exc:  # noqa: BLE001 — per-calendar failure is expected sometimes
            print(f"calendar failed {url}: {exc}")

    if successes == 0:
        print("no calendar accepted the digest — proof NOT written")
        return 1

    out = args.out or args.path + ".ots"
    with open(out, "wb") as fd:
        detached.serialize(StreamSerializationContext(fd))
    print(f"proof written: {out} ({successes}/{len(CALENDARS)} calendars, "
          f"Bitcoin attestation pending; run `ots upgrade` later)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
