"""Sealed Evidence Ledger: append-only, hash-chained, SQLite-backed.

Every entry commits to the previous entry's hash, so editing or deleting any row
breaks `verify()`. UPDATE/DELETE are also refused at the database level.
"""

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from .canonical import canonical_json, sha256_hex

GENESIS = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    seq INTEGER PRIMARY KEY,
    lineage_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_lineage ON entries(lineage_id);
CREATE TRIGGER IF NOT EXISTS no_update BEFORE UPDATE ON entries
    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete BEFORE DELETE ON entries
    BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    lineage_id: str
    stage: str
    kind: str
    payload: dict
    payload_hash: str
    prev_hash: str
    entry_hash: str
    created_at: str


def _entry_hash(seq, lineage_id, stage, kind, payload_hash, prev_hash, created_at) -> str:
    return sha256_hex([seq, lineage_id, stage, kind, payload_hash, prev_hash, created_at])


class EvidenceLedger:
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def append(self, lineage_id: str, stage: str, kind: str, payload: dict) -> LedgerEntry:
        payload_json = canonical_json(payload)
        payload_hash = sha256_hex(payload_json.encode())
        with self._lock:
            row = self._conn.execute("SELECT seq, entry_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev_hash = (row[0] + 1, row[1]) if row else (1, GENESIS)
            created_at = datetime.now(timezone.utc).isoformat()
            entry_hash = _entry_hash(seq, lineage_id, stage, kind, payload_hash, prev_hash, created_at)
            self._conn.execute(
                "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)",
                (seq, lineage_id, stage, kind, payload_json, payload_hash, prev_hash, entry_hash, created_at),
            )
        return LedgerEntry(seq, lineage_id, stage, kind, payload, payload_hash, prev_hash, entry_hash, created_at)

    def entries(self, lineage_prefix: str | None = None, kind: str | None = None) -> list[LedgerEntry]:
        sql, args = "SELECT * FROM entries WHERE 1=1", []
        if lineage_prefix:
            sql += " AND (lineage_id = ? OR lineage_id LIKE ?)"
            args += [lineage_prefix, lineage_prefix + ".%"]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        rows = self._conn.execute(sql + " ORDER BY seq", args).fetchall()
        return [self._row(r) for r in rows]

    def latest(self, lineage_id: str, kind: str) -> LedgerEntry | None:
        found = self.entries(lineage_id, kind)
        return found[-1] if found else None

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the chain. Returns (ok, first_bad_seq)."""
        prev = GENESIS
        for r in self._conn.execute("SELECT * FROM entries ORDER BY seq"):
            e = self._row(r)
            if (
                e.prev_hash != prev
                or sha256_hex(canonical_json(e.payload).encode()) != e.payload_hash
                or _entry_hash(e.seq, e.lineage_id, e.stage, e.kind, e.payload_hash, e.prev_hash, e.created_at) != e.entry_hash
            ):
                return False, e.seq
            prev = e.entry_hash
        return True, None

    @staticmethod
    def _row(r) -> LedgerEntry:
        import json

        return LedgerEntry(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6], r[7], r[8])
