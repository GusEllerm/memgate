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
            self._db.execute("CREATE TABLE IF NOT EXISTS label_sets (id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, labels TEXT NOT NULL)")
            self._db.commit()

    def register(self, labels: LabelSet) -> str:
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO label_sets (id, key, labels) VALUES (?, ?, ?)",
                             (labels.id, labels.key, json.dumps(sorted(str(l) for l in labels.labels))))
            self._db.commit()
        return labels.id

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
