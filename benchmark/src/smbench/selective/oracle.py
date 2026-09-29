"""The answer key: which (agent, location) may recall each fact, decided by memgate's Cedar policies
applied to the ground truth (the label sets of the conversations each fact was stated in). Independent
of every system under test."""

from __future__ import annotations

from memgate.derivation import conversation_labels, personal_labels, personal_note_labels
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World as MemgateWorld

from smbench.selective.world import World


def memgate_world(world: World) -> MemgateWorld:
    spec = world.memgate_world()
    mw = MemgateWorld()
    for e in spec["environments"]:
        mw.add_environment(e["id"], carry_out=e["carry_out"])
    for l in spec["locations"]:
        mw.add_location(l["id"], l["environment"], l["high_assurance"])
    mw.add_agents(*spec["agents"])
    return mw


def permitted_carry_outs(world: World, pol: Policy) -> list[tuple[dict, bool]]:
    """Every carry-out attempt with whether memgate's policy allows it."""
    out = []
    for c in world.conversations:
        src = conversation_labels(c.location, c.participants)
        for co in c.carry_outs:
            out.append(({**co, "conversation": c.id}, pol.may_carry_out(co["agent"], src, world.facts[co["fact"]].kind)))
    return out


def expected(world: World) -> dict[tuple[str, str, str], bool]:
    mw = memgate_world(world)
    reg = Registry()
    holders: dict[str, set[str]] = {f: set() for f in world.facts}     # fact -> label sets holding it
    for c in world.conversations:
        ls = conversation_labels(c.location, c.participants)
        reg.register(ls)
        for f in c.facts:
            holders[f].add(ls.id)
    pol = Policy(mw, reg)
    for co, allowed in permitted_carry_outs(world, pol):              # S4/S5: only permitted carry-outs exist
        if allowed:
            holders[co["fact"]].add(reg.register(personal_labels(co["agent"])))
    for n in world.notes:                                              # S5: personal notes kept in a location
        holders[n["fact"]].add(reg.register(personal_note_labels(n["agent"], n["location"])))
    out = {}
    for agent in world.agents:
        for loc in world.locations:
            allowed = pol.allowed_ids(agent, loc)
            for f, sets in holders.items():
                out[(agent, loc, f)] = bool(sets & allowed)
    return out


def probe_kind(world: World, agent: str, loc: str, fact: str) -> str:
    """Classify a probe for reporting: the agent's relation to the fact at this location."""
    for n in world.notes:
        if n["fact"] == fact:
            if n["agent"] != agent:
                return "note-other-agent"
            return "note-here" if n["location"] == loc else "note-elsewhere"
    for c in world.conversations:
        for co in c.carry_outs:
            if co["fact"] == fact and co["agent"] == agent and loc != c.location:
                kind, env_types = world.facts[fact].kind, world.environments.get(world.env_of(c.location), [])
                if c.location in world.high_assurance:
                    return "carry-refused-ha"
                return f"carried-{kind}" if kind in env_types else f"carry-refused-{kind}"
    if any(fact in c.facts and c.location in world.high_assurance for c in world.conversations):
        stated = [c for c in world.conversations if fact in c.facts]
        if any(agent in c.participants for c in stated):
            return "ha-witness-inside" if loc in world.high_assurance else "ha-witness-outside"
        return "non-witness"
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
