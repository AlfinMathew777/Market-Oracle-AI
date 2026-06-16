"""The Trust Ledger — a tamper-evident, hash-chained audit log.

This is the "prove why" foundation (Articles A1/A2). Every trust decision is
appended as an immutable entry whose hash includes the previous entry's hash —
exactly like a blockchain or a Git commit history. Any after-the-fact edit to a
past decision breaks the chain from that point on, so tampering is detectable by
re-walking the hashes.

  entry_hash = sha256( seq || prev_hash || canonical_json(payload) )
  genesis prev_hash = "0" * 64

Why this matters for "world's most trusted": a prediction platform's value is
its track record. If the record can be quietly edited, the track record is
worthless. A hash-chained ledger makes the history mathematically defensible —
you can hand an auditor the chain and they can verify nothing was altered.

Storage is SQLite (stdlib sqlite3, run off the event loop via asyncio.to_thread)
so the ledger has zero extra dependencies and works in tests without the app DB.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_GENESIS_HASH = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trust_ledger (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    issued_at   TEXT    NOT NULL,
    ticker      TEXT    NOT NULL,
    decision    TEXT    NOT NULL,
    trust_score INTEGER NOT NULL,
    prev_hash   TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    entry_hash  TEXT    NOT NULL UNIQUE
);
"""


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    prev_hash: str
    entry_hash: str


def _canonical(payload: dict) -> str:
    """Deterministic JSON — sorted keys, no whitespace — so hashes are stable."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(seq: int, prev_hash: str, payload: dict) -> str:
    blob = f"{seq}|{prev_hash}|{_canonical(payload)}".encode()
    return hashlib.sha256(blob).hexdigest()


class TrustLedger:
    """Append-only hash-chained store of trust decisions."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = asyncio.Lock()  # Serialise appends so the chain stays linear.

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    async def append(self, payload: dict, *, ticker: str, decision: str,
                     trust_score: int, issued_at: str) -> LedgerEntry:
        """Append one decision, chaining it to the current tip. Returns the entry.

        Serialised by an async lock so concurrent predictions cannot interleave
        and fork the chain.
        """
        async with self._lock:
            return await asyncio.to_thread(
                self._append_sync, payload, ticker, decision, trust_score, issued_at)

    def _append_sync(self, payload: dict, ticker: str, decision: str,
                     trust_score: int, issued_at: str) -> LedgerEntry:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT seq, entry_hash FROM trust_ledger ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = row["entry_hash"] if row else _GENESIS_HASH
            next_seq = (row["seq"] + 1) if row else 1
            entry_hash = compute_hash(next_seq, prev_hash, payload)
            conn.execute(
                "INSERT INTO trust_ledger "
                "(seq, issued_at, ticker, decision, trust_score, prev_hash, payload, entry_hash) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (next_seq, issued_at, ticker, decision, trust_score,
                 prev_hash, _canonical(payload), entry_hash),
            )
            conn.commit()
            return LedgerEntry(seq=next_seq, prev_hash=prev_hash, entry_hash=entry_hash)
        finally:
            conn.close()

    async def verify_chain(self) -> tuple[bool, int | None]:
        """Re-walk the chain. Returns (intact, first_broken_seq).

        Recomputes each entry's hash from its stored seq/prev_hash/payload and
        confirms it matches the stored hash AND that prev_hash links to the prior
        entry. A False result with a seq pinpoints where tampering began.
        """
        return await asyncio.to_thread(self._verify_sync)

    def _verify_sync(self) -> tuple[bool, int | None]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT seq, prev_hash, payload, entry_hash FROM trust_ledger ORDER BY seq ASC"
            ).fetchall()
        finally:
            conn.close()
        expected_prev = _GENESIS_HASH
        for r in rows:
            payload = json.loads(r["payload"])
            recomputed = compute_hash(r["seq"], r["prev_hash"], payload)
            if r["prev_hash"] != expected_prev or recomputed != r["entry_hash"]:
                return False, r["seq"]
            expected_prev = r["entry_hash"]
        return True, None

    async def tip(self) -> LedgerEntry | None:
        return await asyncio.to_thread(self._tip_sync)

    def _tip_sync(self) -> LedgerEntry | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT seq, prev_hash, entry_hash FROM trust_ledger ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return LedgerEntry(seq=row["seq"], prev_hash=row["prev_hash"], entry_hash=row["entry_hash"])
