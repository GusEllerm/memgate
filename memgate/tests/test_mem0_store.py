"""memgate's Mem0 store against a fake `mem0.Memory` with mem0ai 2.2.0's signatures (keyword-only, `top_k`
not `limit`, result dicts with "memory", "user_id", "metadata", "score"), so the store's contract is tested
without Mem0's LLM: scoping by label set, the OR filter, emulated idempotent replace, the verbatim
fallback when extraction keeps nothing, delete by write ID, list and stats shapes, the lock."""

import sys
import types
import uuid
from datetime import datetime

import pytest

from memgate.context import Gate
from memgate.core import Memory
from memgate.derivation import personal_labels
from memgate.store import Item


class FakeMem0:
    """Keeps memories in a list; honours user_id scoping, the OR filter and top_k (default 20, like Mem0)."""

    def __init__(self):
        self.rows: list[dict] = []
        self.extract = lambda text: [text]           # what add(infer=True) "extracts"; tests swap it
        self.locked_during: list[bool] = []
        self.store_ref = None

    @classmethod
    def from_config(cls, config):
        inst = cls()
        inst.config = config
        return inst

    def add(self, messages, *, user_id=None, agent_id=None, run_id=None, metadata=None, infer=True, **kw):
        if self.store_ref is not None:
            self.locked_during.append(self.store_ref._lock.locked())
        texts = [m["content"] for m in messages] if not infer else [t for m in messages for t in self.extract(m["content"])]
        out = []
        for t in texts:
            if infer and any(r["memory"] == t and r["user_id"] == user_id for r in self.rows):
                continue                                   # Mem0 dedups a fact already in the scope
            row = {"id": uuid.uuid4().hex, "memory": t, "user_id": user_id, "agent_id": agent_id, "metadata": dict(metadata or {})}
            self.rows.append(row)
            out.append({**row, "event": "ADD"})
        return {"results": out}

    def _match(self, row, filters):
        if "OR" in filters:
            return row["agent_id"] == filters.get("agent_id") and any(row["user_id"] == c["user_id"] for c in filters["OR"])
        return row["user_id"] == filters["user_id"]

    def get_all(self, *, filters=None, top_k=20, **kw):
        return {"results": [dict(r) for r in self.rows if self._match(r, filters)][:top_k]}

    def search(self, query, *, top_k=20, filters=None, threshold=0.1, **kw):
        hits = [{**r, "score": 0.9 - 0.01 * n} for n, r in enumerate(self.rows) if self._match(r, filters)]
        return {"results": hits[:top_k]}

    def delete(self, memory_id):
        before = len(self.rows)
        self.rows = [r for r in self.rows if r["id"] != memory_id]
        if len(self.rows) == before:
            raise ValueError("unknown memory")


@pytest.fixture
def mem0(monkeypatch):
    fake_module = types.ModuleType("mem0")
    fake_module.Memory = FakeMem0
    monkeypatch.setitem(sys.modules, "mem0", fake_module)
    return fake_module


@pytest.fixture
def store(mem0, world, registry, tmp_path):
    from memgate.adapters.mem0 import Mem0Store
    s = Mem0Store(Gate(world, registry, "s"), tmp_path / "mem0", llm={"provider": "openai", "config": {"model": "m"}})
    s.memory.store_ref = s
    return s


def item(text, ls, wid=None, partition="b", when=None):
    return Item(text=text, label_set=ls, write_id=wid or f"w_{ls}_{uuid.uuid4().hex[:16]}", partition=partition, when=when)


def test_put_scopes_by_label_set_with_the_constant_tag_and_full_metadata(store):
    from memgate.adapters.mem0.store import TAG
    ls = personal_labels("ada").id
    store.put(item("the kiln runs hot", ls, when=datetime(2026, 10, 6, 12)), agent="ada", location="lab")
    (row,) = store.memory.rows
    assert row["user_id"] == ls and row["agent_id"] == TAG
    assert row["metadata"]["label_set"] == ls and row["metadata"]["partition"] == "b" and row["metadata"]["when"].startswith("2026-10-06")
    assert "write_id" in row["metadata"] and "about" not in row["metadata"]
    assert all(store.memory.locked_during)                 # the lock is held across add


def test_idempotent_replace_even_beyond_mem0s_default_page(store):
    ls = personal_labels("ada").id
    for n in range(25):
        store.put(item(f"fact {n}", ls), agent="ada", location="lab")
    wid = f"w_{ls}_{'a' * 16}"
    store.put(item("v1", ls, wid), agent="ada", location="lab")
    store.put(item("v2", ls, wid), agent="ada", location="lab")
    mine = [r for r in store.memory.rows if r["metadata"]["write_id"] == wid]
    assert [r["memory"] for r in mine] == ["v2"]           # 27 rows in the scope: the page was big enough
    assert len(store.memory.rows) == 26


def test_a_write_whose_extraction_keeps_nothing_is_stored_verbatim(store):
    ls = personal_labels("ada").id
    store.memory.extract = lambda text: []
    store.put(item("hello there", ls, f"w_{ls}_{'b' * 16}"), agent="ada", location="lab")
    assert [r["memory"] for r in store.memory.rows] == ["hello there"]
    assert store.delete("b", f"w_{ls}_{'b' * 16}") is True and store.memory.rows == []


def test_search_filters_and_hit_fields(store):
    from memgate.adapters.mem0.store import TAG, filters_for
    a, b, c = personal_labels("ada").id, personal_labels("bo").id, personal_labels("cy").id
    for ls, text in ((a, "ada's"), (b, "bo's"), (c, "cy's")):
        store.put(item(text, ls, when=datetime(2026, 1, 2)), agent="x", location="lab")
    assert store.search(["b"], "q", set(), 5, agent="ada", location="lab") == []
    assert [h.text for h in store.search(["b"], "q", {a}, 5, agent="ada", location="lab")] == ["ada's"]
    hits = store.search(["b"], "q", {a, b}, 5, agent="ada", location="lab")
    assert sorted(h.text for h in hits) == ["ada's", "bo's"] and all(h.when == "2026-01-02" and h.write_id for h in hits)
    assert filters_for([a, b]) == {"agent_id": TAG, "OR": [{"user_id": a}, {"user_id": b}]}
    assert filters_for([]) is None and filters_for([a]) == {"user_id": a}


def test_delete_removes_only_that_write_and_reports_unknown_ids(store):
    ls = personal_labels("ada").id
    w1, w2 = f"w_{ls}_{'1' * 16}", f"w_{ls}_{'2' * 16}"
    store.put(item("one", ls, w1), agent="ada", location="lab")
    store.put(item("two", ls, w2), agent="ada", location="lab")
    assert store.delete("b", w1) is True and [r["memory"] for r in store.memory.rows] == ["two"]
    assert store.delete("b", w1) is False and store.delete("b", "not-a-write-id") is False


def test_list_and_stats_shapes(store):
    ls = personal_labels("ada").id
    store.put(item("kept", ls, when=datetime(2026, 3, 4)), agent="ada", location="lab")
    (listed,) = store.list("b", ls)
    assert listed.label_set == ls and listed.text == "kept" and listed.when == "2026-03" and listed.kind == "memory"
    st = store.stats("b", [ls])
    assert st["label_sets"][ls] == {"memories": 1, "observations": 0, "documents": 1, "last_write": "2026-03"}


def test_memory_over_mem0_makes_the_same_decisions(store, world, registry):
    from memgate.context import Context
    mem = Memory(Gate(world, registry, "s"), store, shared="b")
    ada = Context("ada", "lab", ("ada", "bo"))
    mem.remember(ada, "the kiln runs hot")
    kept = mem.carry_out(ada, "kept", "fact")
    with pytest.raises(PermissionError):
        mem.remember(Context("ada", "nowhere"), "x")
    assert [r.text for r in mem.recall(ada, "kiln")] == ["the kiln runs hot", "kept"]
    assert [r.text for r in mem.recall(Context("cy", "lab"), "kiln")] == []
    assert [i.text for i in mem.personal("ada")] == ["kept"]
    assert mem.forget("ada", kept) is True and mem.personal("ada") == []
