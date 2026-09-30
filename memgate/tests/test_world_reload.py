"""A running gate follows changes to the world file, and ignores a file it can't read."""

import json

from memgate.context import Gate
from memgate.derivation import conversation_labels
from memgate.registry import Registry


def write(path, high_assurance_vault: bool, agents=("ada", "bo")):
    path.write_text(json.dumps({
        "environments": [{"id": "campus"}],
        "locations": [{"id": "lab", "environment": "campus"},
                      {"id": "vault", "environment": "campus", "high_assurance": high_assurance_vault}],
        "agents": list(agents)}))


def test_gate_reloads_a_changed_world(tmp_path):
    path = tmp_path / "world.json"
    write(path, high_assurance_vault=False)
    from memgate.context import load_world
    gate = Gate(load_world(path), Registry(), "s", world_path=path, check_every=0)
    vault = gate.registry.register(conversation_labels("vault", ["ada"]))
    assert not gate.world.high_assurance("vault")
    assert gate.policy.may_carry_out("ada", "vault", conversation_labels("vault", ["ada"]), "fact")

    write(path, high_assurance_vault=True, agents=("ada", "bo", "cy"))   # the vault becomes high assurance
    assert gate.world.high_assurance("vault") and "cy" in gate.world.agents
    assert not gate.policy.may_carry_out("ada", "vault", conversation_labels("vault", ["ada"]), "fact")
    assert vault in gate.policy.allowed_ids("ada", "vault")            # decisions recomputed, not cached
    assert vault not in gate.policy.allowed_ids("ada", "lab")


def test_gate_keeps_the_last_good_world(tmp_path):
    path = tmp_path / "world.json"
    write(path, high_assurance_vault=True)
    from memgate.context import load_world
    gate = Gate(load_world(path), Registry(), "s", world_path=path, check_every=0)
    path.write_text('{"environments": [')                               # caught mid-write
    assert gate.world.high_assurance("vault")
    assert gate.reload_errors == 1


def test_gate_checks_at_most_every_interval(tmp_path):
    path = tmp_path / "world.json"
    write(path, high_assurance_vault=False)
    from memgate.context import load_world
    gate = Gate(load_world(path), Registry(), "s", world_path=path, check_every=3600)
    write(path, high_assurance_vault=True)
    assert not gate.world.high_assurance("vault")                       # not yet looked
    assert gate.refresh(force=True) and gate.world.high_assurance("vault")
