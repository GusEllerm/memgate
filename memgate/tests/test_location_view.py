"""The location's view and purge (0.8.0): a place's conversation memory can be listed with its participants
and hard-deleted, derived items and the private notes bound to it included; personal sets carried out of
the place are left alone, and notes are purged but never listed."""

import asyncio

import pytest

from memgate.context import Context, Gate
from memgate.core import AsyncMemory, Memory
from memgate.derivation import conversation_labels, personal_labels, personal_note_labels
from memgate.store import Capabilities, Hit, Listed

from test_core import FakeStore


class Deriving(FakeStore):
    """A store that builds one derived item per write in the write's own label set, deleted with it."""
    def __init__(self):
        super().__init__()
        self.derived: dict[str, Listed] = {}

    def put(self, item, *, agent, location):
        super().put(item, agent=agent, location=location)
        self.derived[f"d_{item.write_id}"] = Listed(f"d_{item.write_id}", item.label_set, f"derived: {item.text}", kind="derived", sources=[item.write_id])

    def list(self, partition, label_set):
        return super().list(partition, label_set) + [d for d in self.derived.values() if d.label_set == label_set]

    def search(self, partitions, query, allowed, k, *, agent, location):
        hits = super().search(partitions, query, allowed, k, agent=agent, location=location)
        return hits + [Hit(d.text, d.label_set, None, d.write_id, 0.01) for d in self.derived.values() if d.label_set in allowed]

    def delete(self, partition, write_id):
        self.derived.pop(f"d_{write_id}", None)                    # taken with its write, as Hindsight does
        if write_id in self.derived:
            del self.derived[write_id]; return True
        return super().delete(partition, write_id)


@pytest.fixture
def filled(world, registry):
    mem = Memory(Gate(world, registry, "s"), Deriving(), shared="b")
    lab = Context("ada", "lab", ("ada", "bo"))
    mem.remember(lab, "ada and bo spoke in the lab")
    mem.remember(Context("ada", "lab", ("ada", "cy")), "ada and cy spoke in the lab")
    mem.remember(Context("ada", "cafe", ("ada", "bo")), "ada and bo spoke in the cafe")
    mem.keep_note(lab, "ada's private lab note")
    kept = mem.carry_out(lab, "ada took this from the lab", "fact")
    return mem, kept


def test_the_location_view_lists_conversation_sets_with_participants_and_nothing_else(filled):
    mem, kept = filled
    listed = mem.location("lab")
    assert sorted((i.text, tuple(i.participants), i.kind) for i in listed) == [
        ("ada and bo spoke in the lab", ("ada", "bo"), "memory"), ("ada and cy spoke in the lab", ("ada", "cy"), "memory"),
        ("derived: ada and bo spoke in the lab", ("ada", "bo"), "derived"), ("derived: ada and cy spoke in the lab", ("ada", "cy"), "derived")]
    assert {i.label_set for i in listed} == {conversation_labels("lab", ["ada", "bo"]).id, conversation_labels("lab", ["ada", "cy"]).id}
    assert [i.text for i in mem.location("cafe")] == ["ada and bo spoke in the cafe", "derived: ada and bo spoke in the cafe"]
    with pytest.raises(KeyError):
        mem.location("nowhere")
    assert mem.personal("ada")[0].participants == []             # the field is for conversation sets


def test_forgetting_a_location_removes_its_conversations_and_notes_but_not_carry_outs(filled):
    mem, kept = filled
    assert mem.forget_location("lab") == {"sets": 2, "writes": 2, "derived": 2, "notes": 1}
    assert mem.location("lab") == []
    assert [r.text for r in mem.recall(Context("ada", "lab", ("ada", "bo")), "spoke") if "spoke" in r.text] == []   # a participant recalls nothing of it
    assert [r.text for r in mem.recall(Context("ada", "lab"), "note") if "note" in r.text] == []   # the note went too
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "took") if "took" in r.text] == ["ada took this from the lab", "derived: ada took this from the lab"]
    assert [i.text for i in mem.location("cafe")] == ["ada and bo spoke in the cafe", "derived: ada and bo spoke in the cafe"]
    assert mem.forget_location("lab") == {"sets": 0, "writes": 0, "derived": 0, "notes": 0}   # idempotent
    assert mem.forget("ada", kept) is True
    assert personal_note_labels("ada", "lab").id in mem.gate.registry.all()            # the registry keeps the set: ids are content-addressed


def test_location_stats_cover_the_locations_sets(filled):
    mem, _ = filled
    st = mem.stats(location="lab")
    assert st["b"]["items"] >= 1
    with pytest.raises(NotImplementedError):
        Memory(mem.gate, type("Plain", (FakeStore,), {"capabilities": Capabilities()})(), shared="b").forget_location("lab")


def test_the_async_client_does_the_same(world, registry):
    mem = AsyncMemory(Gate(world, registry, "s"), Deriving(), shared="b")

    async def go():
        lab = Context("ada", "lab", ("ada", "bo"))
        await mem.remember(lab, "spoken in the lab")
        await mem.keep_note(lab, "noted in the lab")
        listed = await mem.location("lab")
        assert [(i.text, i.participants) for i in listed] == [("spoken in the lab", ["ada", "bo"]), ("derived: spoken in the lab", ["ada", "bo"])]
        assert await mem.forget_location("lab") == {"sets": 1, "writes": 1, "derived": 1, "notes": 1}
        assert await mem.location("lab") == [] and (await mem.stats(location="lab"))["b"]["items"] == 0
    asyncio.run(go())


def test_a_high_assurance_locations_memory_is_in_its_partition_and_in_the_shared_one_if_it_was_open_before(world, registry):
    from memgate.derivation import conversation_labels
    from memgate.store import Item
    mem = Memory(Gate(world, registry, "s"), Deriving(), shared="b")
    vault = Context("ada", "vault", ("ada", "bo"))
    mem.remember(vault, "said inside the vault")
    ls = mem.gate.registry.register(conversation_labels("vault", ["ada", "bo"]))
    early = Item(text="said before the vault was high-assurance", label_set=ls, write_id=f"w_{ls}_{'e' * 16}", partition="b")
    mem.store.put(early, agent="ada", location="vault")                                 # recorded while the place was open
    assert mem.core.partitions_holding(conversation_labels("vault", ["ada", "bo"])) == ["b--ha--vault", "b"]
    assert sorted(i.text for i in mem.location("vault") if i.kind == "memory") == ["said before the vault was high-assurance", "said inside the vault"]
    assert mem.forget_location("vault") == {"sets": 1, "writes": 2, "derived": 2, "notes": 0}
    assert mem.location("vault") == [] and mem.location("lab") == []
    with pytest.raises(KeyError):
        mem.forget_location("nowhere")


def test_derived_items_the_store_leaves_behind_are_deleted_in_a_second_pass_and_counted_only_when_gone(world, registry):
    class Lingering(Deriving):
        """Like Hindsight listing observations as units: a derived id is not a document, and here the store does not
        take derived items with their writes either, so the purge's second pass must."""
        def delete(self, partition, write_id):
            if write_id in self.derived:
                del self.derived[write_id]; return True
            return FakeStore.delete(self, partition, write_id)

    class Stuck(Lingering):
        def delete(self, partition, write_id):
            if write_id in self.derived:
                return False                                                             # a derived item that cannot be deleted
            return FakeStore.delete(self, partition, write_id)

    for store, derived_count, left in ((Lingering(), 1, 0), (Stuck(), 0, 1)):
        mem = Memory(Gate(world, registry, "s"), store, shared="b")
        mem.remember(Context("ada", "lab", ("ada", "bo")), "spoken")
        assert mem.forget_location("lab") == {"sets": 1, "writes": 1, "derived": derived_count, "notes": 0}
        assert len(mem.location("lab")) == left
