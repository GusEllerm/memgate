"""Classes of personal memory (0.5.0): a fourth label kind that makes a separate personal set, read exactly
like the agent's other personal memory, never consolidated with it, and never moved to a less strict class."""

import json
import random

import pytest

from memgate.derivation import conversation_labels, derived_labels, personal_labels, personal_note_labels
from memgate.labels import CLASSES, Label, LabelSet, class_rank, strictest
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World
from memgate.worldcheck import check_world

U = "unattributed"


# -- labels --------------------------------------------------------------------------------------------
def test_a_class_is_a_label_kind_with_a_closed_ordered_list():
    assert CLASSES[0] == U and class_rank(None) == 0 and class_rank(U) == 1
    assert strictest([]) is None and strictest([None, U]) == U
    with pytest.raises(ValueError):
        Label("class", "unatributed")                                  # a misspelt class fails loudly
    with pytest.raises(ValueError):
        class_rank("secret")


def test_a_class_needs_a_self_and_comes_alone():
    assert LabelSet.build(selfs=["ada"], classes=[U]).classes == {U}
    with pytest.raises(ValueError):
        LabelSet.build(locs=["lab"], withs=["ada", "bo"], classes=[U])  # not on conversation sets
    with pytest.raises(ValueError):
        LabelSet.of(["class:unattributed"])


def test_the_class_set_is_a_different_label_set():
    plain, unnamed = personal_labels("ada"), personal_labels("ada", U)
    assert plain == LabelSet.build(selfs=["ada"]) and unnamed.classes == {U}
    assert plain.id != unnamed.id and unnamed.selfs == plain.selfs
    assert LabelSet.of(json.loads(json.dumps(sorted(str(l) for l in unnamed.labels)))) == unnamed


def test_derived_memory_keeps_the_strictest_class():
    d = derived_labels([personal_labels("ada", U), personal_labels("ada")])
    assert d.classes == {U} and d.selfs == {"ada"}
    assert derived_labels([conversation_labels("lab", ["ada", "bo"])]).classes == frozenset()


# -- reading: exactly as {self:A} ------------------------------------------------------------------------
def test_a_class_set_gets_the_same_decisions_as_the_plain_personal_set(world, registry, policy):
    for a in sorted(world.agents):
        registry.register(personal_labels(a))
        registry.register(personal_labels(a, U))
    for reader in sorted(world.agents):
        for loc in sorted(world.locations):
            allowed = policy.allowed_ids(reader, loc)
            assert allowed == policy.allowed_ids_exact(reader, loc)
            for owner in sorted(world.agents):
                assert (personal_labels(owner).id in allowed) == (personal_labels(owner, U).id in allowed)
                assert (personal_labels(owner).id in allowed) == (owner == reader)       # owner only, everywhere
            assert policy.may_write(reader, loc, personal_labels(reader, U)) == policy.may_write(reader, loc, personal_labels(reader))


def test_compiled_filter_matches_cedar_with_classes():
    rng = random.Random(77)
    for _ in range(150):
        w = World()
        w.add_environment("e")
        locs = [f"l{i}" for i in range(rng.randint(2, 4))]
        for i, l in enumerate(locs):
            w.add_location(l, "e", high_assurance=(i == 0 and rng.random() < 0.6))
        agents = [f"a{i}" for i in range(rng.randint(2, 5))]
        w.add_agents(*agents)
        reg = Registry()
        for _ in range(rng.randint(5, 30)):
            selfs = rng.sample(agents, rng.choice([0, 1, 1, 2]))
            reg.register(LabelSet.build(selfs=selfs, locs=rng.sample(locs, rng.choice([0, 0, 1])),
                                        withs=rng.sample(agents, rng.randint(0, 2)),
                                        classes=[U] if selfs and rng.random() < 0.5 else []))
        pol = Policy(w, reg)
        for a in agents:
            for l in locs:
                pol._residual_where(a, l)
                assert pol.allowed_ids(a, l) == pol.allowed_ids_exact(a, l), (a, l)


# -- a newer memgate's rows fail closed, one set at a time -------------------------------------------------
def test_a_label_set_this_version_cannot_read_is_skipped_not_fatal(world, tmp_path):
    reg = Registry(tmp_path / "r.sqlite")
    mine = reg.register(personal_labels("ada"))
    with reg._lock:                                       # as written by a future memgate
        for id_, labels in [("ls_future_kind", ["self:ada", "mood:calm"]), ("ls_future_class", ["self:ada", "class:secret"])]:
            reg._db.execute("INSERT INTO label_sets (id, key, labels) VALUES (?, ?, ?)", (id_, "|".join(labels), json.dumps(labels)))
            reg._db.executemany("INSERT INTO label (label_set, kind, value) VALUES (?, ?, ?)",
                                [(id_, *l.split(":", 1)) for l in labels])
        reg._db.commit()
    assert set(reg.all()) == {mine}                       # the validator's view: unknown sets aren't registered
    pol = Policy(world, reg)
    assert pol.allowed_ids("ada", "lab") == {mine} == pol.allowed_ids_exact("ada", "lab")


# -- the world's minimum class ------------------------------------------------------------------------------
def test_min_class_in_the_world_file():
    good = {"environments": [{"id": "open"}, {"id": "slick", "carry_out": ["fact", "opinion", "skill"], "min_class": U}],
            "locations": [{"id": "lab", "environment": "open"}, {"id": "shade", "environment": "slick"}], "agents": ["ada"]}
    assert check_world(good) == []
    bad = json.loads(json.dumps(good))
    bad["environments"][1]["min_class"] = "anonymous"
    assert any("min_class" in e for e in check_world(bad))
    w = World()
    w.add_environment("open")
    w.add_environment("slick", min_class=U)
    w.add_location("lab", "open")
    w.add_location("shade", "slick")
    assert w.min_class({"lab"}) is None and w.min_class({"shade"}) == U and w.min_class({"lab", "shade"}) == U
    before = w.fingerprint()
    w.add_environment("open", min_class=U)
    assert w.fingerprint() != before


def test_notes_are_untouched():
    assert personal_note_labels("ada", "lab").classes == frozenset()
