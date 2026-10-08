"""When something is missing or broken, memgate refuses; it never falls back to allowing."""

import urllib.error

import pytest

from memgate.context import Context, Gate
from memgate.derivation import conversation_labels, personal_labels


def test_unknown_agent_or_location_is_refused_everything(policy, registry):
    registry.register(personal_labels("ada"))
    for agent, loc in (("ada", "nowhere"), ("zed", "lab")):
        assert policy.allowed_ids(agent, loc) == set()
        assert policy.allowed_ids_exact(agent, loc) == set()
        assert not policy.may_write(agent, loc, personal_labels(agent))
        assert not policy.may_carry_out(agent, loc, personal_labels(agent), "fact")


def test_an_unreachable_memory_store_raises_rather_than_returning_nothing_checked(world, registry):
    from memgate.adapters.hindsight.client import HindsightMemory
    mem = HindsightMemory(Gate(world, registry, "s"), bank="b", base_url="http://127.0.0.1:9", timeout=2)
    with pytest.raises((urllib.error.URLError, OSError)):
        mem.recall(Context("ada", "lab"), "anything")
    with pytest.raises((urllib.error.URLError, OSError)):
        mem.remember(Context("ada", "lab", ("ada", "bo")), "anything")


def test_a_refused_write_never_reaches_the_store(world, registry):
    from memgate.adapters.hindsight.client import HindsightMemory
    mem = HindsightMemory(Gate(world, registry, "s"), bank="b", base_url="http://127.0.0.1:9", timeout=2)
    with pytest.raises(PermissionError):                       # refused before any network call
        mem.remember(Context("ada", "nowhere", ("ada", "bo")), "A place the world doesn't list.")
    with pytest.raises(PermissionError):
        mem.carry_out(Context("ada", "vault"), "From the vault.", "opinion", source=personal_labels("ada"))
    assert len(registry) == 0                                   # nothing was even registered


def test_a_broken_registry_raises(policy, registry):
    registry.register(conversation_labels("lab", ["ada"]))
    registry._db.close()
    with pytest.raises(Exception):
        policy.allowed_ids("ada", "lab")


def test_label_sets_naming_a_location_the_world_no_longer_lists_give_refusals_not_errors(tmp_path):
    """0.8.2: a tree removed from the world (or a world reloaded while a write was in flight) leaves label sets that
    name a location the world doesn't list. Every decision about them is a refusal, never a KeyError."""
    import json
    from memgate.context import Context, Gate, load_world
    from memgate.core import Memory
    from memgate.derivation import conversation_labels
    from memgate.registry import Registry
    from test_core import FakeStore
    path = tmp_path / "world.json"
    spec = {"environments": [{"id": "open"}], "locations": [{"id": "lab", "environment": "open"},
            {"id": "vault", "environment": "open", "high_assurance": True}], "agents": ["ada", "bo"]}
    path.write_text(json.dumps(spec))
    gate = Gate(load_world(path), Registry(), "s", world_path=path, check_every=0)
    mem = Memory(gate, FakeStore(), shared="b")
    mem.remember(Context("ada", "vault", ("ada", "bo")), "said in the vault")
    mem.remember(Context("ada", "lab", ("ada", "bo")), "said in the lab")
    spec["locations"] = [{"id": "lab", "environment": "open"}]                     # the vault is removed
    path.write_text(json.dumps(spec))
    vault_set = conversation_labels("vault", ["ada", "bo"])
    assert gate.world.high_assurance("vault") is False and gate.world.carry_out_types(frozenset({"vault"})) == frozenset()
    assert mem.recall(Context("ada", "vault", ("ada", "bo")), "said") == []          # unlisted location: nothing, no error
    assert gate.policy.may_write("ada", "vault", vault_set) is False
    assert gate.policy.may_carry_out("ada", "lab", vault_set, "fact") is False
    assert gate.policy.allowed_ids("ada", "lab") == gate.policy.allowed_ids_exact("ada", "lab")
    assert [r.text for r in mem.recall(Context("ada", "lab", ("ada", "bo")), "said") if "lab" in r.text] == ["said in the lab"]


def test_an_empty_world_is_valid_and_refuses_everything(tmp_path):
    """0.8.2: a fresh deployment's world lists no locations or agents; it loads, every call is refused, and the gate
    picks up the populated world when the file changes."""
    import json
    from memgate.context import Context, Gate, load_world
    from memgate.core import Memory
    from memgate.registry import Registry
    from memgate.worldcheck import check_world_file, world_file_warnings
    from test_core import FakeStore
    path = tmp_path / "world.json"
    spec = {"agents": [], "locations": [], "environments": [{"id": "open"}], "classes": [{"id": "unattributed", "consolidate": False}]}
    path.write_text(json.dumps(spec))
    assert check_world_file(path) == []
    assert len(world_file_warnings(path)) == 2
    gate = Gate(load_world(path), Registry(), "s", world_path=path, check_every=0)
    mem = Memory(gate, FakeStore(), shared="b")
    with pytest.raises(PermissionError):
        mem.remember(Context("ada", "lab", ("ada",)), "too early")
    assert mem.recall(Context("ada", "lab"), "anything") == []
    with pytest.raises(KeyError):
        mem.location("lab")
    spec.update(locations=[{"id": "lab", "environment": "open"}], agents=["ada"])
    path.write_text(json.dumps(spec))                                              # the host plants the first tree
    mem.remember(Context("ada", "lab", ("ada",)), "now it is remembered")
    assert [r.text for r in mem.recall(Context("ada", "lab", ("ada",)), "remembered")] == ["now it is remembered"]


def test_a_world_reloaded_mid_write_never_routes_a_high_assurance_write_to_the_shared_partition(tmp_path):
    """0.8.2: the write's decision and its routing use one snapshot of the world. A reload between them (here, the
    vault removed while the label set is being registered) must not send a vault write to the shared partition."""
    import json
    from memgate.context import Context, Gate, load_world
    from memgate.core import Memory
    from memgate.registry import Registry
    from test_core import FakeStore
    path = tmp_path / "world.json"
    spec = {"environments": [{"id": "open"}], "locations": [{"id": "lab", "environment": "open"},
            {"id": "vault", "environment": "open", "high_assurance": True}], "agents": ["ada", "bo"]}
    path.write_text(json.dumps(spec))
    registry = Registry()
    gate = Gate(load_world(path), registry, "s", world_path=path, check_every=0)
    mem = Memory(gate, FakeStore(), shared="b")
    original = registry.register

    def register_while_the_vault_is_removed(labels):
        spec["locations"] = [{"id": "lab", "environment": "open"}]
        path.write_text(json.dumps(spec))
        gate.refresh(force=True)
        return original(labels)
    registry.register = register_while_the_vault_is_removed
    wid = mem.remember(Context("ada", "vault", ("ada", "bo")), "vault secret")
    assert mem.store.items[wid].partition == "b--ha--vault"                      # decided and routed with the same world
    registry.register = original
    with pytest.raises(PermissionError):                                          # and now the vault is gone, refused
        mem.remember(Context("ada", "vault", ("ada", "bo")), "too late")


def test_compiled_filter_matches_cedar_when_label_sets_name_unlisted_locations():
    """0.8.2: random worlds whose registry holds label sets naming locations the world no longer lists (as locations
    and as carry-out sources): the compiled filter still equals Cedar's exact answer, and nothing that names an
    unlisted location is readable, since no reader can stand in a location the world doesn't list."""
    import random
    from memgate.labels import LabelSet
    from memgate.policy import Policy
    from memgate.registry import Registry
    from memgate.world import World
    rng = random.Random(82)
    for _ in range(80):
        w = World()
        w.add_environment("open"); w.add_environment("held", carry_out=())
        listed = [f"l{i}" for i in range(rng.randint(1, 4))]
        gone = [f"gone{i}" for i in range(rng.randint(1, 2))]
        for i, l in enumerate(listed):
            w.add_location(l, rng.choice(["open", "held"]), high_assurance=(i == 0 and rng.random() < 0.4))
        agents = [f"a{i}" for i in range(rng.randint(1, 3))]
        w.add_agents(*agents)
        reg = Registry()
        for _ in range(rng.randint(3, 20)):
            if rng.random() < 0.5:
                reg.register(LabelSet.build(locs=rng.sample(listed + gone, 1), withs=rng.sample(agents, rng.randint(1, len(agents)))))
            else:
                reg.register(LabelSet.build(selfs=[rng.choice(agents)], srcs=rng.sample(listed + gone, rng.choice([0, 1]))))
        pol = Policy(w, reg)
        for a in agents:
            for l in listed:
                allowed = pol.allowed_ids(a, l)
                assert allowed == pol.allowed_ids_exact(a, l), (a, l)
                assert not any(set(reg.get(i).locs) & set(gone) for i in allowed)      # no reader can stand in a gone location
