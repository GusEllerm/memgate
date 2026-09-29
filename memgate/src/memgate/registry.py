"""The label-set registry: every label combination in use, keyed by its content-addressed ID.

Memory systems store only the opaque ID; the registry is how the policy layer knows what an ID
means. Registration is idempotent, so any process can register the label set it is writing.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from memgate.labels import LabelSet


class Registry:
    def __init__(self, path: str | Path = ":memory:"):
        self._db = sqlite3.connect(str(path), check_same_thread=False)
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
                f"SELECT ls.id FROM label_sets ls WHERE ls.rowid > ? AND ({where})", [after] + params)}
            newest = self._db.execute("SELECT COALESCE(MAX(rowid), 0) FROM label_sets").fetchone()[0]
        return ids, newest

    def get(self, id: str) -> LabelSet:
        with self._lock:
            row = self._db.execute("SELECT labels FROM label_sets WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown label set {id}")
        return LabelSet.of(json.loads(row[0]))

    def all(self) -> dict[str, LabelSet]:
        with self._lock:
            rows = self._db.execute("SELECT id, labels FROM label_sets").fetchall()
        return {id: LabelSet.of(json.loads(labels)) for id, labels in rows}

    def __len__(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM label_sets").fetchone()[0]
