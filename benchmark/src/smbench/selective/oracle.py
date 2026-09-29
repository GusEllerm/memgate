"""The answer key: which (agent, location) may recall each fact, decided by memgate's Cedar policies
applied to the ground truth (the label sets of the conversations each fact was stated in). Independent
of every system under test."""

from __future__ import annotations

from memgate.derivation import conversation_labels
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World as MemgateWorld

from smbench.selective.world import World


def expected(world: World) -> dict[tuple[str, str, str], bool]:
    mw = MemgateWorld()
    mw.add_environment("env")
    for l in world.locations:
        mw.add_location(l, "env")
    mw.add_agents(*world.agents)
    reg = Registry()
    holders: dict[str, set[str]] = {f: set() for f in world.facts}     # fact -> label sets stating it
    for c in world.conversations:
        ls = conversation_labels(c.location, c.participants)
        reg.register(ls)
        for f in c.facts:
            holders[f].add(ls.id)
    pol = Policy(mw, reg)
    out = {}
    for agent in world.agents:
        for loc in world.locations:
            allowed = pol.allowed_ids(agent, loc)
            for f, sets in holders.items():
                out[(agent, loc, f)] = bool(sets & allowed)
    return out


def probe_kind(world: World, agent: str, loc: str, fact: str) -> str:
    """Classify a probe for reporting: the agent's relation to the fact at this location."""
    by_id = {c.id: c for c in world.conversations}
    stated_in = [c for c in world.conversations if fact in c.facts]
    here = [c for c in stated_in if agent in c.participants and c.location == loc]
    if here:
        newcomer = any(fact in c.retells and agent not in by_id[c.retells[fact]].participants for c in here)
        return "retold-to-newcomer" if newcomer else "witness-here"
    if any(agent in c.participants for c in stated_in):
        return "witness-elsewhere"
    for r in world.conversations:                       # the fact A and B shared but A did not retell
        for told, src_id in r.retells.items():
            src = by_id[src_id]
            if fact in src.facts and fact != told and agent in r.participants and agent not in src.participants:
                return "untold-to-newcomer"
    return "non-witness"
