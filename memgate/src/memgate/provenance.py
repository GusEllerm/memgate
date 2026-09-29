"""Provenance and audit: where every memory came from, including across agents.

Records three kinds of event:
- a recall: who recalled, where, what they asked, which label sets were allowed, what came back;
- a turn: what an agent said, where, to whom, and which recalls it drew on;
- a write: a stored memory, its label set, and the turns (or memories) it was formed from.

That makes a memory's origin recoverable across agents: memory -> the turns it came from -> the
recalls behind those turns -> the memories they returned -> ... When A retells an {A,B}
conversation to C, the memory C forms points back to what A recalled.

The log is itself memory, so it is partitioned like memory: each high-assurance location gets its
own store, and nothing recorded there (not even that a recall happened) reaches the shared store.

Trails are shown to someone through the same rules as recall:
- a source they can read is shown in full;
- a source they can't read shows only that it exists and where it came from (the "existence
  visible" choice for provenance, docs/vault/Concepts/Label and Memory Types.md), and nothing of
  what it was built from;
- a high-assurance source they can't read is left out entirely.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from memgate.policy import Policy
from memgate.world import World

SHARED = "shared"

SCHEMA = """
CREATE TABLE IF NOT EXISTS recalls (id TEXT PRIMARY KEY, ts REAL, agent TEXT, location TEXT, query TEXT,
                                    allowed TEXT, returned TEXT);
CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, ts REAL, speaker TEXT, location TEXT, participants TEXT,
                                  text TEXT, recalls TEXT);
CREATE TABLE IF NOT EXISTS writes (id TEXT PRIMARY KEY, ts REAL, author TEXT, location TEXT, label_set TEXT,
                                   kind TEXT, text TEXT, turns TEXT, derived_from TEXT);
CREATE TABLE IF NOT EXISTS audit (ts REAL, event TEXT, detail TEXT);
"""


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


@dataclass
class TrailNode:
    """One memory in a provenance trail, as the asker is allowed to see it."""
    write_id: str
    visibility: str                 # "full" or "existence"
    location: str | None = None
    kind: str | None = None
    text: str | None = None
    author: str | None = None
    sources: list["TrailNode"] = field(default_factory=list)


class ProvenanceLog:
    def __init__(self, root: str | Path, world: World):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.world = world
        self._dbs: dict[str, sqlite3.Connection] = {}
        self._lock = threading.Lock()

    # -- partitions --------------------------------------------------------------------------------
    def partition(self, location: str | None) -> str:
        """High-assurance locations keep their own log; everything else shares one."""
        if location and location in self.world.locations and self.world.high_assurance(location):
            return f"ha-{location}"
        return SHARED

    def _db(self, partition: str) -> sqlite3.Connection:
        if partition not in self._dbs:
            db = sqlite3.connect(str(self.root / f"provenance-{partition}.sqlite"), check_same_thread=False)
            db.executescript(SCHEMA)
            self._dbs[partition] = db
        return self._dbs[partition]

    def _insert(self, location: str | None, sql: str, row: tuple) -> None:
        with self._lock:
            db = self._db(self.partition(location))
            db.execute(sql, row)
            db.commit()

    # -- recording ---------------------------------------------------------------------------------
    def record_recall(self, agent: str, location: str, query: str, allowed: set[str],
                      returned: list[tuple[str, str]]) -> str:
        """`returned` is [(write_id, label_set_id)] for each memory the recall gave back."""
        rid = new_id("rc")
        self._insert(location, "INSERT INTO recalls VALUES (?,?,?,?,?,?,?)",
                     (rid, time.time(), agent, location, query, json.dumps(sorted(allowed)), json.dumps(returned)))
        return rid

    def record_turn(self, speaker: str, location: str, participants: list[str], text: str, recalls: list[str]) -> str:
        tid = new_id("tn")
        self._insert(location, "INSERT INTO turns VALUES (?,?,?,?,?,?,?)",
                     (tid, time.time(), speaker, location, json.dumps(sorted(participants)), text, json.dumps(recalls)))
        return tid

    def record_write(self, write_id: str, author: str, location: str, label_set: str, kind: str, text: str, *,
                     turns: list[str] = (), derived_from: list[str] = ()) -> None:
        self._insert(location, "INSERT INTO writes VALUES (?,?,?,?,?,?,?,?,?)",
                     (write_id, time.time(), author, location, label_set, kind, text,
                      json.dumps(list(turns)), json.dumps(list(derived_from))))

    def audit(self, location: str | None, event: str, **detail) -> None:
        self._insert(location, "INSERT INTO audit VALUES (?,?,?)", (time.time(), event, json.dumps(detail, default=str)))

    # -- reading -----------------------------------------------------------------------------------
    def _find(self, table: str, id_: str, partitions: list[str]) -> tuple[str, sqlite3.Row] | None:
        with self._lock:
            for p in partitions:
                db = self._db(p)
                db.row_factory = sqlite3.Row
                row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (id_,)).fetchone()
                db.row_factory = None
                if row is not None:
                    return p, row
        return None

    def _partitions_visible_from(self, location: str) -> list[str]:
        """The shared log, plus the asker's own high-assurance partition if they are inside one."""
        own = self.partition(location)
        return [SHARED] if own == SHARED else [own, SHARED]

    def sources_of(self, write_id: str, partitions: list[str]) -> list[str]:
        """Write IDs a memory was formed from: via its turns' recalls, and directly via derived_from."""
        found = self._find("writes", write_id, partitions)
        if not found:
            return []
        _, w = found
        out: list[str] = list(json.loads(w["derived_from"]))
        for tid in json.loads(w["turns"]):
            t = self._find("turns", tid, partitions)
            if not t:
                continue
            for rid in json.loads(t[1]["recalls"]):
                r = self._find("recalls", rid, partitions)
                if r:
                    out += [ref for ref, _ in json.loads(r[1]["returned"])]
        return list(dict.fromkeys(out))

    def trail(self, write_id: str, asker: str, location: str, policy: Policy, depth: int = 3) -> TrailNode | None:
        """The provenance trail of a memory as `asker` at `location` may see it (None if sealed)."""
        allowed = policy.allowed_ids(asker, location)
        partitions = self._partitions_visible_from(location)

        def node(wid: str, d: int, seen: set[str]) -> TrailNode | None:
            found = self._find("writes", wid, partitions)
            if not found:
                return None  # unknown, or recorded in a high-assurance partition the asker is outside
            _, w = found
            if w["label_set"] in allowed:
                n = TrailNode(wid, "full", w["location"], w["kind"], w["text"], w["author"])
            elif self.partition(w["location"]) != SHARED:
                return None  # a sealed high-assurance source: not even its existence is shown
            else:
                n = TrailNode(wid, "existence", w["location"])
            # Only a memory the asker can read shows what it was built from.
            if n.visibility == "full" and d > 0 and wid not in seen:
                for src in self.sources_of(wid, partitions):
                    child = node(src, d - 1, seen | {wid})
                    if child:
                        n.sources.append(child)
            return n

        return node(write_id, depth, set())
