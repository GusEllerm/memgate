"""The compiled residual filter must give exactly Cedar's answer."""

import random

import pytest

from memgate.labels import NOBODY, LabelSet
from memgate.policy import POLICIES, Policy
from memgate.registry import Registry
from memgate.residual import Unsupported
from memgate.world import World

TOO_BROAD = '\n@id("too-broad")\npermit (principal == Agent::"a0", action == Action::"read", resource);\n'
UNFAMILIAR = '\n@id("one-set")\npermit (principal, action == Action::"read", resource == LabelSet::"ls_x");\n'


def random_world(rng: random.Random) -> tuple[World, Registry, list[str], list[str]]:
    w = World()
    w.add_environment("e")
    locs = [f"l{i}" for i in range(rng.randint(2, 5))]
    for i, l in enumerate(locs):
        w.add_location(l, "e", high_assurance=(i == 0 and rng.random() < 0.7))
    agents = [f"a{i}" for i in range(rng.randint(2, 6))]
    w.add_agents(*agents)
    reg = Registry()
    for _ in range(rng.randint(5, 40)):
        withs = rng.sample(agents, rng.randint(0, min(3, len(agents))))
        if rng.random() < 0.1:
            withs = [NOBODY]
        reg.register(LabelSet.build(selfs=rng.sample(agents, rng.choice([0, 0, 0, 1, 2])),
                                    locs=rng.sample(locs, rng.choice([0, 1, 1, 1, 2])), withs=withs))
    return w, reg, agents, locs


@pytest.mark.parametrize("extra", ["", TOO_BROAD], ids=["policies", "policies+over-broad-grant"])
def test_compiled_filter_matches_cedar(extra):
    rng = random.Random(1234)
    checked = 0
    for _ in range(300):
        w, reg, agents, locs = random_world(rng)
        pol = Policy(w, reg, policies=POLICIES + extra)
        for a in agents:
            for l in locs:
                pol._residual_where(a, l)                        # must compile, not fall back
                assert pol.allowed_ids(a, l) == pol.allowed_ids_exact(a, l), (a, l)
                checked += 1
    assert checked > 1000


def test_unfamiliar_policy_falls_back_to_cedar():
    rng = random.Random(7)
    w, reg, agents, locs = random_world(rng)
    pol = Policy(w, reg, policies=POLICIES + UNFAMILIAR)
    with pytest.raises(Unsupported):
        pol._residual_where(agents[0], locs[0])
    assert pol.allowed_ids(agents[0], locs[0]) == pol.allowed_ids_exact(agents[0], locs[0])


def test_cache_picks_up_new_label_sets_and_world_changes():
    w = World()
    w.add_environment("e")
    w.add_location("lab", "e")
    w.add_location("vault", "e")
    w.add_agents("ada", "bo")
    reg = Registry()
    pol = Policy(w, reg)
    first = LabelSet.build(locs=["lab"], withs=["ada"])
    reg.register(first)
    assert pol.allowed_ids("ada", "lab") == {first.id}
    second = LabelSet.build(locs=["lab"], withs=["ada", "bo"])
    reg.register(second)                                   # registered after the first call was cached
    assert pol.allowed_ids("ada", "lab") == {first.id, second.id}
    note = LabelSet.build(selfs=["ada"], locs=["vault"])
    reg.register(note)
    assert note.id in pol.allowed_ids("ada", "vault")
    w.locations["vault"] = type(w.locations["vault"])("vault", "e", high_assurance=True)   # world changes
    assert pol.allowed_ids("ada", "vault") == pol.allowed_ids_exact("ada", "vault")
