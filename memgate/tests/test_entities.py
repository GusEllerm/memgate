"""The entity attributes memgate hands Cedar must be computed correctly.

The formal proofs (proofs/, SymCC) hold for any attribute values, but two guarantees depend on what
the values mean, which Cedar cannot check (it cannot loop over a set's members):
- haLocs is exactly the high-assurance locations among locs (proof R5: nothing formed in a
  high-assurance location is recalled outside it);
- carryTypes is exactly the memory types every location's environment lets out (proof C2).
This test checks both, and each Location's highAssurance, on random worlds.
"""

import random

from memgate.labels import NOBODY, LabelSet
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import MEMORY_TYPES, World


def random_world(rng: random.Random):
    w = World()
    envs = [f"e{i}" for i in range(rng.randint(1, 4))]
    carry = {e: frozenset(rng.sample(sorted(MEMORY_TYPES), rng.randint(0, len(MEMORY_TYPES)))) for e in envs}
    for e in envs:
        w.add_environment(e, carry_out=carry[e])
    locs = {f"l{i}": (rng.choice(envs), rng.random() < 0.3) for i in range(rng.randint(2, 6))}
    for l, (e, ha) in locs.items():
        w.add_location(l, e, high_assurance=ha)
    agents = [f"a{i}" for i in range(rng.randint(2, 5))]
    w.add_agents(*agents)
    reg = Registry()
    for _ in range(rng.randint(5, 30)):
        withs = rng.sample(agents, rng.randint(0, min(3, len(agents)))) if rng.random() > 0.1 else [NOBODY]
        reg.register(LabelSet.build(selfs=rng.sample(agents, rng.choice([0, 0, 1, 2])),
                                    locs=rng.sample(sorted(locs), min(len(locs), rng.choice([0, 1, 1, 2, 3]))), withs=withs))
    return w, reg, locs, carry


def test_entity_attributes_mean_what_the_proofs_assume():
    rng = random.Random(99)
    checked = 0
    for _ in range(300):
        w, reg, locs, carry = random_world(rng)
        pol = Policy(w, reg)
        ents = {(e["uid"]["type"], e["uid"]["id"]): e["attrs"] for e in pol._entities(reg.all())}
        for l, (env, ha) in locs.items():
            assert ents[("Location", l)]["highAssurance"] is ha
        for id_, ls in reg.all().items():
            attrs = ents[("LabelSet", id_)]
            ha_locs = {x["__entity"]["id"] for x in attrs["haLocs"]}
            assert ha_locs == {l for l in ls.locs if locs[l][1]}, (ls, attrs)
            expected = set(MEMORY_TYPES)
            for l in ls.locs:
                expected &= carry[locs[l][0]]
            assert set(attrs["carryTypes"]) == expected, (ls, attrs)
            checked += 1
    assert checked > 1000
