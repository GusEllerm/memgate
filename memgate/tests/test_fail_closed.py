"""When something is missing or broken, memgate refuses; it never falls back to allowing."""

import urllib.error

import pytest

from memgate.context import Gate
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
        mem.recall("ada", "lab", "anything")
    with pytest.raises((urllib.error.URLError, OSError)):
        mem.remember("ada", "lab", ["ada", "bo"], "anything")


def test_a_refused_write_never_reaches_the_store(world, registry):
    from memgate.adapters.hindsight.client import HindsightMemory
    mem = HindsightMemory(Gate(world, registry, "s"), bank="b", base_url="http://127.0.0.1:9", timeout=2)
    with pytest.raises(PermissionError):                       # refused before any network call
        mem.remember("dee", "lab", ["ada", "bo"], "Dee plants a memory.")
    with pytest.raises(PermissionError):
        mem.carry_out("ada", "vault", personal_labels("ada"), "From the vault.", "opinion")
    assert len(registry) == 0                                   # nothing was even registered


def test_a_broken_registry_raises(policy, registry):
    registry.register(conversation_labels("lab", ["ada"]))
    registry._db.close()
    with pytest.raises(Exception):
        policy.allowed_ids("ada", "lab")
