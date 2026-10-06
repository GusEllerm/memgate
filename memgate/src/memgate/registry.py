"""The label-set registry: every label combination in use, keyed by its content-addressed ID.

Memory systems store only the opaque ID; the registry is how the policy layer knows what an ID
means. Registration is idempotent, so any process can register the label set it is writing: several
host processes (e.g. web workers) may share one registry. Two backends behind one class:

- **SQLite** (a path): one file on one host. SQLite serialises writers (a writer waits up to `timeout`
  seconds for the lock), so row IDs stay in commit order, which the policy's incremental cache relies
  on (`select_ids`). tests/test_registry_processes.py checks it. Never on NFS/EFS.
- **PostgreSQL** (a `postgresql://` URL; since 0.6.0, `pip install 'memgate[postgres]'`): for hosts whose
  workers run on more than one machine. Tables live in the `memgate` schema, so the registry can share
  the database Hindsight uses. Registration takes a transaction-scoped advisory lock, so sequence
  numbers commit in order, the same guarantee SQLite gives for free.

The residual compiler (memgate.residual) emits a WHERE clause over `label_sets ls` with `?` placeholders
and EXISTS subqueries on `label l`; both backends run it, the Postgres one after turning `?` into `%s`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from memgate.labels import CLASSES, KINDS, LabelSet

# Rows this version can read: every label of a known kind, and a class label of a known class. A label
# set written by a newer memgate with a kind or class this one doesn't know is skipped (never readable,
# never writable here) rather than failing every call that reads the registry.
_KNOWN = (f"(u.kind IN ({','.join('?' * (len(KINDS) - 1))}) OR (u.kind = 'class' AND u.value IN ({','.join('?' * len(CLASSES))})))")
_KNOWN_PARAMS = [k for k in KINDS if k != "class"] + list(CLASSES)
_ADVISORY_LOCK_KEY = 0x6D656D67          # "memg": one lock for every registration in a database


def _parse_all(rows) -> dict[str, LabelSet]:
    out = {}
    for id_, labels in rows:
        try:
            out[id_] = LabelSet.of(json.loads(labels))
        except ValueError:
            continue                    # written by a newer memgate: fail closed for that set only
    return out


class Registry:
    """`Registry(path)` for SQLite (default: in memory), `Registry("postgresql://...")` for PostgreSQL."""

    def __new__(cls, path: str | Path = ":memory:", timeout: float = 30.0):
        if cls is Registry and isinstance(path, str) and path.startswith(("postgresql://", "postgres://")):
            return super().__new__(PostgresRegistry)
        return super().__new__(cls)

    def __init__(self, path: str | Path = ":memory:", timeout: float = 30.0):
        self.path = str(path)
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=timeout)
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript("""
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS label_sets (id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, labels TEXT NOT NULL);
                -- One row per label, so set conditions compile to indexed EXISTS / NOT EXISTS (memgate.residual).
                CREATE TABLE IF NOT EXISTS label (label_set TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL,
                                                  PRIMARY KEY (label_set, kind, value));
                CREATE INDEX IF NOT EXISTS label_by_value ON label (kind, value);
            """)
            missing = self._db.execute(
                "SELECT id, labels FROM label_sets WHERE id NOT IN (SELECT DISTINCT label_set FROM label)").fetchall()
            for id_, labels in missing:       # registries created before the label table existed
                self._insert_labels(id_, LabelSet.of(json.loads(labels)))
            self._db.commit()

    def _insert_labels(self, id_: str, labels: LabelSet) -> None:
        self._db.executemany("INSERT OR IGNORE INTO label (label_set, kind, value) VALUES (?, ?, ?)",
                             [(id_, l.kind, l.value) for l in labels.labels])

    def register(self, labels: LabelSet) -> str:
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO label_sets (id, key, labels) VALUES (?, ?, ?)",
                                   (labels.id, labels.key, json.dumps(sorted(str(l) for l in labels.labels))))
            if cur.rowcount:
                self._insert_labels(labels.id, labels)
            self._db.commit()
        return labels.id

    def select_ids(self, where: str, params: list, after: int = 0) -> tuple[set[str], int]:
        """Label-set IDs matching a WHERE clause over `label_sets ls` (see memgate.residual), among those
        registered after row `after`; also returns the newest row seen. The registry is append-only,
        so callers can cache a result and later ask only about label sets registered since."""
        with self._lock:
            ids = {r[0] for r in self._db.execute(
                f"SELECT ls.id FROM label_sets ls WHERE ls.rowid > ? AND ({where}) "
                f"AND NOT EXISTS (SELECT 1 FROM label u WHERE u.label_set = ls.id AND NOT {_KNOWN})",
                [after] + params + _KNOWN_PARAMS)}
            newest = self._db.execute("SELECT COALESCE(MAX(rowid), 0) FROM label_sets").fetchone()[0]
        return ids, newest

    def get(self, id: str) -> LabelSet:
        with self._lock:
            row = self._db.execute("SELECT labels FROM label_sets WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown label set {id}")
        return LabelSet.of(json.loads(row[0]))

    def all(self) -> dict[str, LabelSet]:
        """Every registered label set this version can read (see _KNOWN; unreadable rows are left out)."""
        with self._lock:
            rows = self._db.execute("SELECT id, labels FROM label_sets").fetchall()
        return _parse_all(rows)

    def __len__(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM label_sets").fetchone()[0]


class PostgresRegistry(Registry):
    """The registry in PostgreSQL (schema `memgate`). One connection per instance, autocommit off; every
    public method is one transaction. Needs psycopg 3 (`memgate[postgres]`)."""

    def __init__(self, path: str, timeout: float = 30.0):
        import psycopg
        self.path = path
        self._lock = threading.Lock()
        self._db = psycopg.connect(path, connect_timeout=int(timeout), autocommit=False)
        with self._lock, self._db.transaction():
            self._db.execute("CREATE SCHEMA IF NOT EXISTS memgate")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS memgate.label_sets (
                    seq BIGSERIAL PRIMARY KEY, id TEXT UNIQUE NOT NULL, key TEXT UNIQUE NOT NULL, labels TEXT NOT NULL)""")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS memgate.label (label_set TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL,
                                                          PRIMARY KEY (label_set, kind, value))""")
            self._db.execute("CREATE INDEX IF NOT EXISTS label_by_value ON memgate.label (kind, value)")

    @staticmethod
    def _pg(sql: str) -> str:
        """The SQLite-flavoured SQL the compiler emits, for PostgreSQL: placeholders and table names."""
        return (sql.replace("?", "%s").replace("FROM label_sets ls", "FROM memgate.label_sets ls")
                .replace("FROM label l", "FROM memgate.label l").replace("FROM label u", "FROM memgate.label u"))

    def register(self, labels: LabelSet) -> str:
        with self._lock, self._db.transaction():
            # Serialise registrations, so `seq` commits in order and `select_ids(after=)` never misses a row
            # whose commit overtook a higher sequence number.
            self._db.execute("SELECT pg_advisory_xact_lock(%s)", (_ADVISORY_LOCK_KEY,))
            cur = self._db.execute(
                "INSERT INTO memgate.label_sets (id, key, labels) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (labels.id, labels.key, json.dumps(sorted(str(l) for l in labels.labels))))
            if cur.rowcount:
                with self._db.cursor() as c:
                    c.executemany("INSERT INTO memgate.label (label_set, kind, value) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                  [(labels.id, l.kind, l.value) for l in labels.labels])
        return labels.id

    def select_ids(self, where: str, params: list, after: int = 0) -> tuple[set[str], int]:
        sql = self._pg(f"SELECT ls.id FROM label_sets ls WHERE ls.seq > ? AND ({where}) "
                       f"AND NOT EXISTS (SELECT 1 FROM label u WHERE u.label_set = ls.id AND NOT {_KNOWN})")
        with self._lock, self._db.transaction():
            ids = {r[0] for r in self._db.execute(sql, [after] + params + _KNOWN_PARAMS)}
            newest = self._db.execute("SELECT COALESCE(MAX(seq), 0) FROM memgate.label_sets").fetchone()[0]
        return ids, int(newest)

    def get(self, id: str) -> LabelSet:
        with self._lock, self._db.transaction():
            row = self._db.execute("SELECT labels FROM memgate.label_sets WHERE id = %s", (id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown label set {id}")
        return LabelSet.of(json.loads(row[0]))

    def all(self) -> dict[str, LabelSet]:
        with self._lock, self._db.transaction():
            rows = self._db.execute("SELECT id, labels FROM memgate.label_sets").fetchall()
        return _parse_all(rows)

    def __len__(self) -> int:
        with self._lock, self._db.transaction():
            return self._db.execute("SELECT COUNT(*) FROM memgate.label_sets").fetchone()[0]

    def copy_from(self, other: Registry) -> int:
        """Migrate another registry's label sets into this one (IDs are content-addressed, so a copy is
        a re-registration). Returns how many were added."""
        before = len(self)
        for ls in other.all().values():
            self.register(ls)
        return len(self) - before
