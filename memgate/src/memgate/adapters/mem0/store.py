"""Mem0 (open source, in process) as a memgate store.

Mem0 scopes everything by `user_id`: add() extracts facts with its LLM, deduplicates them against the
memories already in that scope, and stores the rest; search() filters by scope. memgate uses the label-set
ID as the scope, so Mem0 never deduplicates or links across label sets (label-safe compaction by
construction), and recall is one search with an OR over the label sets the agent may read, ANDed with a
constant `agent_id` that Mem0 requires as a top-level scope key (an OR Qdrant evaluates as "at least one
of these"; another Mem0 vector store may differ).

What Mem0 does not offer, and the capabilities say so: no second lock (Mem0 has no validator hook, so
memgate's client is the only enforcement), no partitions (one collection; a high-assurance location's
memories are kept apart by their label set only, not by storage), no consolidation control (Mem0 has no
derived memories to switch off). Idempotent replace is emulated: a put adds, then removes what the same
write ID stored before. Two approximations, because Mem0 stores extracted facts rather than the text
written: a put whose extraction yields nothing is stored verbatim instead (so every write stays
addressable), and a fact identical to one another write already stored in the scope is not stored
twice, so deleting a write removes what it produced, which may be less than it said. Deletion removes
the vectors; Mem0's own history database (`history.db` beside the collection) keeps the written text
until it is cleaned separately.

Mem0's add(infer=True) extraction runs on every put, through the configured LLM. Calls are serialised:
the local Qdrant client and Mem0's history database are not safe to share across threads.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from memgate.context import Gate
from memgate.store import Capabilities, Hit, Item, Listed

TAG = "memgate"      # a constant agent_id on every write: Mem0's search needs a top-level scope key before it
                     # accepts an OR over user_ids, so the OR is ANDed with this always-true condition

CAPABILITIES = Capabilities(second_lock=False, idempotent_replace=True, partitions=False, delete=True,
                            list_by_label_set=True, stats=True, consolidation_control=False)


def filters_for(scopes: list[str]) -> dict | None:
    """Mem0 search filters for the label sets (scopes) a recall may read: None for none, one `user_id`
    for one, else an OR over them ANDed with the constant tag Mem0 needs as a top-level scope key."""
    if not scopes:
        return None
    if len(scopes) == 1:
        return {"user_id": scopes[0]}
    return {"agent_id": TAG, "OR": [{"user_id": s} for s in scopes]}


class Mem0Store:
    """One Mem0 `Memory` on local Qdrant and fastembed, under memgate."""

    capabilities = CAPABILITIES

    def __init__(self, gate: Gate, path: str | Path, *, llm: dict, embedder: dict | None = None,
                 collection: str = "memgate", embedding_dims: int = 384):
        """`llm` and `embedder` are Mem0 provider configs, e.g. llm={"provider": "openai", "config": {"model": ...,
        "openai_base_url": ..., "api_key": ..., "max_tokens": 8000}}; the embedder defaults to fastembed
        BAAI/bge-small-en-v1.5 (384 dims)."""
        os.environ.setdefault("MEM0_TELEMETRY", "false")
        from mem0 import Memory
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.gate = gate
        self.memory = Memory.from_config({
            "llm": llm,
            "embedder": embedder or {"provider": "fastembed", "config": {"model": "BAAI/bge-small-en-v1.5"}},
            "vector_store": {"provider": "qdrant", "config": {"collection_name": collection, "path": str(path / "qdrant"),
                                                              "embedding_model_dims": embedding_dims}},
            "history_db_path": str(path / "history.db"),
        })
        self._lock = threading.Lock()

    # -- required ---------------------------------------------------------------------------------
    def ensure(self, partition: str, *, consolidate: bool = True) -> None:
        return None                                   # one collection; nothing to create, nothing to switch

    PAGE = 10_000      # Mem0's get_all is one scroll of `top_k`; a personal set this large needs paging instead

    def _items_of(self, label_set: str) -> list[dict]:
        res = self.memory.get_all(filters={"user_id": label_set}, top_k=self.PAGE)
        return list(res.get("results", res) if isinstance(res, dict) else res)

    def put(self, item: Item, *, agent: str | None, location: str | None) -> None:
        metadata = {"write_id": item.write_id, "label_set": item.label_set, "partition": item.partition}
        if item.when:
            metadata["when"] = item.when.isoformat() if hasattr(item.when, "isoformat") else item.when
        if item.about:
            metadata["about"] = item.about
        with self._lock:
            before = [m["id"] for m in self._items_of(item.label_set) if (m.get("metadata") or {}).get("write_id") == item.write_id]
            res = self.memory.add([{"role": "user", "content": item.text}], user_id=item.label_set, agent_id=TAG, metadata=metadata)
            if not (res.get("results") if isinstance(res, dict) else res):
                # Extraction kept nothing (or every fact was already in the scope): keep the text itself, so the
                # write exists, can be listed and forgotten, and replaces its earlier self.
                self.memory.add([{"role": "user", "content": item.text}], user_id=item.label_set, agent_id=TAG,
                                metadata=metadata, infer=False)
            for mid in before:                                  # add first, then drop the earlier version
                self.memory.delete(mid)

    def search(self, partitions: list[str], query: str, allowed: set[str], k: int, *, agent: str | None,
               location: str | None) -> list[Hit]:
        filters = filters_for(sorted(allowed))
        if filters is None:
            return []
        with self._lock:
            res = self.memory.search(query, top_k=k, filters=filters, threshold=0.0)
        out = []
        for r in res.get("results", []):
            md = r.get("metadata") or {}
            ls = md.get("label_set") or r.get("user_id") or ""
            out.append(Hit(r["memory"], ls, (md.get("when") or "")[:10] or None, md.get("write_id"), float(r.get("score") or 0.0)))
        return out

    def pending(self, partitions: list[str]) -> int:
        return 0                                      # add() is synchronous

    # -- capabilities -------------------------------------------------------------------------------
    def delete(self, partition: str, write_id: str) -> bool:
        from memgate.provenance import write_id_label_set
        ls = write_id_label_set(write_id)
        if not ls:
            return False
        existed = False
        with self._lock:
            for m in self._items_of(ls):
                if (m.get("metadata") or {}).get("write_id") == write_id:
                    self.memory.delete(m["id"])
                    existed = True
        return existed

    def list(self, partition: str, label_set: str) -> list[Listed]:
        with self._lock:
            items = self._items_of(label_set)
        out = []
        for m in items:
            md = m.get("metadata") or {}
            out.append(Listed(write_id=md.get("write_id") or m["id"], label_set=label_set, text=m.get("memory", ""),
                              when=(md.get("when") or "")[:7] or None))
        return out

    def stats(self, partition: str, label_sets: list[str] | None = None) -> dict:
        out: dict = {"exists": True, "pending": 0, "last_consolidation": None}
        if label_sets:
            out["label_sets"] = {}
            for ls in label_sets:
                items = self.list(partition, ls)
                out["label_sets"][ls] = {"memories": len(items), "observations": 0,
                                         "documents": len({i.write_id for i in items}),
                                         "last_write": max((i.when or "" for i in items), default=None)}
        return out
