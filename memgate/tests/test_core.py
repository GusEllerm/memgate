"""memgate.core over a fake store: the decisions are the store's business nowhere, and the owner's
operations (forget, personal, stats) rest on the write ID's label set."""

import json
import logging

import pytest

from memgate.context import Context, Gate
from memgate.core import Memory, Recalled
from memgate.derivation import conversation_labels, personal_labels
from memgate.labels import LabelSet
from memgate.provenance import write_id_label_set
from memgate.store import Capabilities, Hit, Item, Listed, Store


class FakeStore:
    """Keeps items in a dict; answers searches with every item in the partitions, scored by order."""
    capabilities = Capabilities(delete=True, list_by_label_set=True, stats=True)

    def __init__(self):
        self.items: dict[str, Item] = {}
        self.ensured: dict[str, bool] = {}
        self.extra: list[Hit] = []            # hits a buggy store might return beyond what it was allowed

    def ensure(self, partition, *, consolidate=True):
        self.ensured[partition] = self.ensured.get(partition, True) and consolidate

    def put(self, item, *, agent, location):
        self.items[item.write_id] = item

    def search(self, partitions, query, allowed, k, *, agent, location):
        hits = [Hit(i.text, i.label_set, None, i.write_id, 1.0 / (n + 1)) for n, i in enumerate(self.items.values())
                if i.partition in partitions]
        return hits + self.extra

    def pending(self, partitions):
        return 0

    def delete(self, partition, write_id):
        return self.items.pop(write_id, None) is not None

    def list(self, partition, label_set):
        return [Listed(i.write_id, i.label_set, i.text) for i in self.items.values() if i.label_set == label_set]

    def stats(self, partition, label_sets=None):
        return {"exists": True, "items": sum(i.partition == partition for i in self.items.values())}


@pytest.fixture
def mem(world, registry):
    world.add_class("unattributed", consolidate=False)
    return Memory(Gate(world, registry, "s"), FakeStore(), shared="b")


def test_the_store_protocol_is_satisfied_by_the_fake():
    assert isinstance(FakeStore(), Store)


def test_decisions_and_routing_without_any_store_knowledge(mem):
    ada = Context("ada", "lab", ("ada", "bo"))
    w = mem.remember(ada, "the kiln runs hot")
    assert mem.store.items[w].partition == "b" and mem.store.items[w].label_set == ada.conversation().id
    v = mem.remember(Context("ada", "vault", ("ada", "bo")), "inside")
    assert mem.store.items[v].partition == "b--ha--vault"                   # a high-assurance partition
    with pytest.raises(PermissionError):
        mem.remember(Context("ada", "nowhere"), "unknown place")
    with pytest.raises(PermissionError):
        mem.carry_out(Context("ada", "vault", ("ada", "bo")), "out", "opinion")
    assert [r.text for r in mem.recall(ada, "kiln")] == ["the kiln runs hot"]
    assert [r.text for r in mem.recall(Context("cy", "lab"), "kiln")] == []     # not a participant
    assert [r.text for r in mem.recall(Context("ada", "vault"), "x")] == ["inside"]   # the lab talk stays in the lab


def test_the_client_side_lock_drops_what_a_store_returns_beyond_the_allowed_sets(mem, caplog):
    ada = Context("ada", "lab", ("ada", "bo"))
    mem.remember(ada, "mine")
    other = mem.gate.registry.register(conversation_labels("lab", ["bo", "cy"]))
    mem.store.extra = [Hit("not for ada", other, None, "w_x", 5.0)]
    with caplog.at_level(logging.INFO, logger="memgate"):
        batch = mem.recall(ada, "anything")
    assert [r.text for r in batch] == ["mine"]
    events = [json.loads(r.getMessage()) for r in caplog.records if r.name == "memgate"]
    recall = next(e for e in events if e["event"] == "recall")
    assert recall["dropped_by_client"] == 1 and recall["returned"] == 1 and "anything" not in json.dumps(events)


def test_a_class_without_consolidation_asks_the_store_for_it(mem):
    ada = Context("ada", "lab", ("ada", "bo"))
    mem.carry_out(ada, "a colleague says the buffer drifts", "fact", cls="unattributed")
    mem.carry_out(ada, "Bo says the buffer drifts", "fact")
    items = list(mem.store.items.values())
    assert [i.consolidate for i in items] == [False, True]
    assert [i.partition for i in items] == ["b--class--unattributed", "b"]   # the class gets its own partition
    assert mem.store.ensured["b--class--unattributed"] is False and mem.store.ensured["b"] is True   # the shared one is untouched
    assert mem.core.partitions() == ["b", "b--class--unattributed", "b--ha--vault"]
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "buffer")] == ["a colleague says the buffer drifts", "Bo says the buffer drifts"]


def test_forget_is_bound_to_the_agents_own_personal_sets(mem):
    ada = Context("ada", "lab", ("ada", "bo"))
    kept = mem.carry_out(ada, "kept", "fact")
    unnamed = mem.carry_out(ada, "unnamed", "fact", cls="unattributed")
    said = mem.remember(ada, "said")
    assert write_id_label_set(kept) == personal_labels("ada").id
    with pytest.raises(PermissionError):
        mem.forget("bo", kept)                   # not Bo's
    with pytest.raises(PermissionError):
        mem.forget("ada", said)                  # a conversation, not personal memory
    assert mem.forget("ada", kept) is True and mem.forget("ada", kept) is False
    assert mem.forget("ada", unnamed) is True
    assert [i.text for i in mem.store.items.values()] == ["said"]


def test_personal_lists_every_personal_set_and_stats_cover_every_partition(mem):
    ada = Context("ada", "lab", ("ada", "bo"))
    mem.carry_out(ada, "kept", "fact")
    mem.carry_out(ada, "unnamed", "fact", cls="unattributed")
    mem.remember(ada, "said")
    listed = mem.personal("ada")
    assert sorted(i.text for i in listed) == ["kept", "unnamed"]
    assert {i.label_set for i in listed} == {personal_labels("ada").id, personal_labels("ada", "unattributed").id}
    assert mem.personal("bo") == []
    st = mem.stats()
    assert set(st) == {"b", "b--class--unattributed", "b--ha--vault"} and st["b"]["items"] == 2 and st["b--class--unattributed"]["items"] == 1


def test_a_store_without_a_capability_is_refused_not_guessed(world, registry):
    class Minimal(FakeStore):
        capabilities = Capabilities()
    m = Memory(Gate(world, registry, "s"), Minimal(), shared="b")
    with pytest.raises(NotImplementedError):
        m.forget("ada", "w_x")
    with pytest.raises(NotImplementedError):
        m.personal("ada")
    with pytest.raises(NotImplementedError):
        m.stats()
