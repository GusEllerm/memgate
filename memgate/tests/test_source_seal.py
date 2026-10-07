"""The source seal (0.7.0): a personal memory carried out of a location whose environment now lets nothing
out is recalled only there; it comes back when the location is released. Both locks derive it from the same
policy; here the compiled filter, Cedar's exact answer, the client, the owner's view and the migration."""

import json
import random

import pytest

from memgate.context import Context, Gate, load_world
from memgate.core import Memory
from memgate.derivation import personal_labels
from memgate.labels import Label, LabelSet
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World

from test_core import FakeStore


def test_a_source_label_needs_a_self_and_is_the_fifth_kind():
    ls = LabelSet.build(selfs=["ada"], srcs=["lab"])
    assert ls.srcs == {"lab"} and ls.id != personal_labels("ada").id
    assert personal_labels("ada", "unattributed", src="lab").srcs == {"lab"}
    with pytest.raises(ValueError):
        LabelSet.build(locs=["lab"], withs=["ada"], srcs=["lab"])          # not on conversation sets
    assert Label.parse("src:lab").kind == "src"


def test_compiled_filter_matches_cedar_with_sources_and_sealed_environments():
    rng = random.Random(11)
    for _ in range(120):
        w = World()
        w.add_environment("open")
        w.add_environment("held", carry_out=())
        w.add_environment("some", carry_out={"opinion"})
        locs = [f"l{i}" for i in range(rng.randint(2, 5))]
        for i, l in enumerate(locs):
            w.add_location(l, rng.choice(["open", "held", "some"]), high_assurance=(i == 0 and rng.random() < 0.3))
        agents = [f"a{i}" for i in range(rng.randint(2, 4))]
        w.add_agents(*agents)
        reg = Registry()
        for _ in range(rng.randint(5, 30)):
            selfs = rng.sample(agents, rng.choice([0, 1, 1]))
            reg.register(LabelSet.build(selfs=selfs, locs=rng.sample(locs, rng.choice([0, 0, 1])) if not selfs or rng.random() < 0.3 else [],
                                        withs=rng.sample(agents, rng.randint(0, 2)) if not selfs else [],
                                        srcs=rng.sample(locs, rng.choice([0, 1, 1, 2])) if selfs else []))
        pol = Policy(w, reg)
        for a in agents:
            for l in locs:
                pol._residual_where(a, l)
                assert pol.allowed_ids(a, l) == pol.allowed_ids_exact(a, l), (a, l)


def test_sealed_srcs_is_computed_as_the_proofs_assume():
    w = World()
    w.add_environment("open"); w.add_environment("held", carry_out=())
    w.add_location("lab", "open"); w.add_location("pen", "held")
    w.add_agents("ada")
    ls = LabelSet.build(selfs=["ada"], srcs=["lab", "pen"])
    ent = Policy(w, Registry())._label_set_entity(ls.id, ls)["attrs"]
    assert [e["__entity"]["id"] for e in ent["srcs"]] == ["lab", "pen"]
    assert [e["__entity"]["id"] for e in ent["sealedSrcs"]] == ["pen"]       # the sources whose environment lets nothing out
    w.add_environment("open", carry_out=())                                    # hold the open one too
    assert [e["__entity"]["id"] for e in Policy(w, Registry())._label_set_entity(ls.id, ls)["attrs"]["sealedSrcs"]] == ["lab", "pen"]


@pytest.fixture
def held_world(tmp_path):
    spec = {"environments": [{"id": "open"}, {"id": "other"}],
            "locations": [{"id": "lab", "environment": "open"}, {"id": "cafe", "environment": "other"}],
            "agents": ["ada", "bo"]}
    path = tmp_path / "world.json"
    path.write_text(json.dumps(spec))
    gate = Gate(load_world(path), Registry(), "s", world_path=path, check_every=0)
    return gate, path, spec


def hold(path, spec, env, held=True):
    for e in spec["environments"]:
        if e["id"] == env:
            if held:
                e["carry_out"] = []
            else:
                e.pop("carry_out", None)
    path.write_text(json.dumps(spec))


def test_holding_a_location_withholds_what_left_it_until_released(held_world):
    gate, path, spec = held_world
    mem = Memory(gate, FakeStore(), shared="b")
    ada = Context("ada", "lab", ("ada", "bo"))
    kept = mem.carry_out(ada, "the kiln runs hot", "fact")
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "kiln")] == ["the kiln runs hot"]
    hold(path, spec, "open")
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "kiln")] == []           # withheld outside the source
    assert [r.text for r in mem.recall(Context("ada", "lab"), "kiln")] == ["the kiln runs hot"]   # kept at the source
    (item,) = mem.personal("ada")
    assert item.source == "lab" and item.withheld is True
    with pytest.raises(PermissionError):                                                # nothing new leaves either
        mem.carry_out(ada, "more", "fact")
    hold(path, spec, "open", held=False)
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "kiln")] == ["the kiln runs hot"]   # released
    assert mem.personal("ada")[0].withheld is False
    assert mem.forget("ada", kept) is True


def test_unsourced_legacy_items_stay_readable_until_a_source_is_attached(held_world):
    from memgate.store import Item
    gate, path, spec = held_world
    mem = Memory(gate, FakeStore(), shared="b")
    legacy_ls = gate.registry.register(personal_labels("ada"))                          # how 0.6.x wrote it
    legacy = f"w_{legacy_ls}_{'d' * 16}"
    mem.store.put(Item(text="kept in 0.6", label_set=legacy_ls, write_id=legacy, partition="b"), agent="ada", location="lab")
    hold(path, spec, "open")
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "kept")] == ["kept in 0.6"]  # no source: not withheld
    (item,) = mem.personal("ada")
    assert item.source is None and item.withheld is False
    assert mem.attach_source("ada", legacy, "lab", dry_run=True) == 1 and mem.store.items[legacy].text == "kept in 0.6"
    assert mem.attach_source("ada", legacy, "lab") == 1
    assert legacy not in mem.store.items
    (item,) = mem.personal("ada")
    assert item.source == "lab" and item.withheld is True and item.text == "kept in 0.6"
    assert [r.text for r in mem.recall(Context("ada", "cafe"), "kept")] == []            # now sealed with its source
    assert mem.attach_source("ada", item.write_id, "lab") == 0                           # already sourced
    with pytest.raises(PermissionError):
        mem.attach_source("bo", item.write_id, "lab")
    with pytest.raises(KeyError):
        mem.attach_source("ada", legacy, "nowhere")
