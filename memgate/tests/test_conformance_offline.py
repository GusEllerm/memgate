"""Conformance over a fake store: which checks run or skip for which capabilities, that owner-view passes on
a correct store and fails on a leaky one, and that cleanup deletes exactly the writes the run made."""

import pytest

from memgate.conformance import CLAIMS, SECOND_LOCK_CHECKS, run
from memgate.context import Gate
from memgate.core import Memory
from memgate.store import Capabilities

from test_core import FakeStore


def world_for_conformance(world):
    world.add_environment("slick", carry_out={"fact", "opinion", "skill"}, min_class="unattributed")
    world.add_location("shade", "slick")
    world.add_class("unattributed", consolidate=False)
    return world


def by_id(checks):
    return {c.id: c for c in checks}


def test_everything_applicable_passes_on_a_correct_fake_store(world, registry):
    gate = Gate(world_for_conformance(world), registry, "s")
    store = FakeStore()
    store.put_log = []
    pre = Memory(gate, store, shared="production")
    checks = by_id(run(gate, memory=pre))
    assert pre.core.shared == "production"                                # the caller's Memory is untouched
    for cid in SECOND_LOCK_CHECKS:
        assert checks[cid].status == "skip"
        assert "second lock" in checks[cid].detail or (cid == "ha-partition-search" and "no partitions" in checks[cid].detail)
    for cid in ("witness", "non-witness", "elsewhere", "carry-out", "carry-refused", "class-carry-out", "class-downgrade",
                "class-minimum", "owner-view", "class-legacy", "ha-inside", "ha-outside", "ha-seal"):
        assert checks[cid].status == "pass", (cid, checks[cid].detail)
    assert checks["ha-partition"].status == "skip" and "no partitions" in checks["ha-partition"].detail
    assert checks["class-apart"].status == "skip" and "derived nothing" in checks["class-apart"].detail
    assert checks["split-scope"].status == "skip"
    assert store.items == {}                                              # every write the run made was deleted


def test_a_store_without_the_owner_capabilities_skips_those_checks(world, registry):
    class Plain(FakeStore):
        capabilities = Capabilities()
    gate = Gate(world_for_conformance(world), registry, "s")
    checks = by_id(run(gate, memory=Memory(gate, Plain(), shared="x")))
    assert checks["owner-view"].status == "skip" and checks["class-apart"].status == "skip" and checks["class-legacy"].status == "skip"
    assert checks["witness"].status == "pass" and checks["class-downgrade"].status == "pass"


def test_owner_view_fails_when_forget_removes_more_than_the_one_item(world, registry):
    class Greedy(FakeStore):
        def delete(self, partition, write_id):
            existed = write_id in self.items
            self.items.clear()                                            # a store that deletes too much
            return existed
    gate = Gate(world_for_conformance(world), registry, "s")
    checks = by_id(run(gate, memory=Memory(gate, Greedy(), shared="x")))
    assert checks["owner-view"].status == "fail" and "did not remove exactly it" in checks["owner-view"].detail


def test_owner_view_fails_when_the_listing_ignores_the_label_set_filter(world, registry):
    from memgate.store import Listed

    class Leaky(FakeStore):
        def list(self, partition, label_set):
            return [Listed(i.write_id, i.label_set, i.text) for i in self.items.values()]   # every item, whatever was asked
    gate = Gate(world_for_conformance(world), registry, "s")
    checks = by_id(run(gate, memory=Memory(gate, Leaky(), shared="x")))
    assert checks["owner-view"].status == "fail"


def test_run_needs_a_target(world, registry):
    with pytest.raises(ValueError):
        run(Gate(world, registry, "s"))


def test_every_claim_is_reported_once(world, registry):
    gate = Gate(world_for_conformance(world), registry, "s")
    checks = run(gate, memory=Memory(gate, FakeStore(), shared="x"))
    assert [c.id for c in checks] == [cid for cid, _ in CLAIMS]
