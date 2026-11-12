"""Sealed Evidence Ledger: append-only, hash-chained, SQLite-backed.

Every entry commits to the previous entry's hash, so editing or deleting any row
breaks `verify()`. UPDATE/DELETE are also refused at the database level.
"""

import hashlib
import hmac
import json
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
CREATE TABLE IF NOT EXISTS checkpoints (
    seq INTEGER PRIMARY KEY,
    head_hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS no_update_checkpoints BEFORE UPDATE ON checkpoints
    BEGIN SELECT RAISE(ABORT, 'checkpoints are append-only'); END;
CREATE TRIGGER IF NOT EXISTS no_delete_checkpoints BEFORE DELETE ON checkpoints
    BEGIN SELECT RAISE(ABORT, 'checkpoints are append-only'); END;
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


def _sign_head(seq: int, head_hash: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{seq}:{head_hash}".encode("utf-8"), hashlib.sha256).hexdigest()


class EvidenceLedger:
    def __init__(self, path: str = ":memory:", clock=None, secret: str | None = None):
        """`clock` returns an aware datetime for each entry. Only seeded history passes one, to spread
        synthetic runs over past days; the timestamp is inside the hash chain either way."""
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._secret = secret
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def append(self, lineage_id: str, stage: str, kind: str, payload: dict) -> LedgerEntry:
        payload_json = canonical_json(payload)
        payload_hash = sha256_hex(payload_json.encode())
        with self._lock:
            row = self._conn.execute("SELECT seq, entry_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
            seq, prev_hash = (row[0] + 1, row[1]) if row else (1, GENESIS)
            created_at = self._clock().isoformat()
            entry_hash = _entry_hash(seq, lineage_id, stage, kind, payload_hash, prev_hash, created_at)
            self._conn.execute(
                "INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)",
                (seq, lineage_id, stage, kind, payload_json, payload_hash, prev_hash, entry_hash, created_at),
            )
            if self._secret:
                sig = _sign_head(seq, entry_hash, self._secret)
                self._conn.execute(
                    "INSERT INTO checkpoints VALUES (?,?,?,?)",
                    (seq, entry_hash, sig, created_at),
                )
        return LedgerEntry(seq, lineage_id, stage, kind, payload, payload_hash, prev_hash, entry_hash, created_at)

    def checkpoint(self, secret: str | None = None) -> dict:
        """Create and return an HMAC-signed head anchor.

        If `secret` is provided, it signs using that key, falling back to `self._secret`.
        """
        sec = secret or self._secret
        with self._lock:
            row = self._conn.execute("SELECT seq, entry_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
            if not row:
                return {"seq": 0, "head_hash": GENESIS, "signature": _sign_head(0, GENESIS, sec) if sec else ""}
            seq, head_hash = row[0], row[1]
            sig = _sign_head(seq, head_hash, sec) if sec else ""
            created_at = self._clock().isoformat()
            exists = self._conn.execute("SELECT 1 FROM checkpoints WHERE seq = ?", (seq,)).fetchone()
            if not exists and sig:
                self._conn.execute(
                    "INSERT INTO checkpoints VALUES (?,?,?,?)",
                    (seq, head_hash, sig, created_at),
                )
            return {"seq": seq, "head_hash": head_hash, "signature": sig, "created_at": created_at}

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

    def _signed(self, seq: int, head_hash: str, signature: str, secret: str | None) -> bool:
        return bool(secret and signature) and hmac.compare_digest(signature, _sign_head(seq, head_hash, secret))

    def _holds(self, seq: int, head_hash: str) -> bool:
        """True if this ledger contains the entry `head_hash` at `seq`: an anchor may be older than the head."""
        if seq == 0:
            return head_hash == GENESIS
        row = self._conn.execute("SELECT entry_hash FROM entries WHERE seq = ?", (seq,)).fetchone()
        return bool(row) and row[0] == head_hash

    def verify(self, secret: str | None = None, checkpoint: dict | None = None) -> tuple[bool, int | None]:
        """Recompute the chain, then check it against head anchors. Returns (ok, first_bad_seq).

        An anchor says "this ledger once had entry H at seq N", so it holds for any ledger that still contains that
        entry, however far it has grown since. Truncation or a rewrite behind the anchor fails it.
        - `checkpoint`: an anchor the caller kept elsewhere. It must carry a valid signature, or it proves nothing.
        - the stored checkpoints: the newest one whose signature verifies. Rows signed under another secret (the key
          was rotated) are ignored rather than read as tampering; the chain itself is still fully checked.
        Stored checkpoints share the database's trust boundary, so on their own they only catch a truncation that left
        them in place. An anchor kept off-machine is what covers the rest."""
        sec = secret or self._secret
        prev = GENESIS
        for r in self._conn.execute("SELECT * FROM entries ORDER BY seq"):
            e = self._row(r)
            if (
                e.prev_hash != prev
                or e.payload_hash != sha256_hex(e.payload)
                or e.entry_hash != _entry_hash(e.seq, e.lineage_id, e.stage, e.kind, e.payload_hash, e.prev_hash, e.created_at)
            ):
                return False, e.seq
            prev = e.entry_hash

        if checkpoint is not None:
            seq, head_hash = int(checkpoint.get("seq", 0)), checkpoint.get("head_hash", GENESIS)
            if not self._signed(seq, head_hash, checkpoint.get("signature", ""), sec) or not self._holds(seq, head_hash):
                return False, seq

        if sec:
            for seq, head_hash, sig in self._conn.execute("SELECT seq, head_hash, signature FROM checkpoints ORDER BY seq DESC"):
                if self._signed(seq, head_hash, sig, sec):
                    if not self._holds(seq, head_hash):
                        return False, seq
                    break
        return True, None

    @staticmethod
    def _row(r) -> LedgerEntry:
        return LedgerEntry(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6], r[7], r[8])


_SHARED: dict[str, EvidenceLedger] = {}
_SHARED_LOCK = threading.Lock()


def open_ledger(path: str, secret: str | None = None) -> EvidenceLedger:
    """One ledger object per file per process. Live runs all append to the same file, and one
    object (one lock) keeps their seq/prev_hash chain from racing. ':memory:' is always private."""
    if path == ":memory:":
        return EvidenceLedger(path, secret=secret)
    with _SHARED_LOCK:
        if path not in _SHARED:
            _SHARED[path] = EvidenceLedger(path, secret=secret)
        elif secret and not _SHARED[path]._secret:
            _SHARED[path]._secret = secret
        return _SHARED[path]
