"""Cedar decisions over label sets.

`allowed_ids` answers "which label sets may this agent read here?". Cedar partially evaluates the
policies with the agent and location known and the label set unknown; memgate.residual compiles the
residual into a SQL filter over the registry, so the answer costs one indexed query however many
label sets exist. If a policy uses something the compiler doesn't handle, it falls back to
`allowed_ids_exact`, which checks every registered label set in one Cedar batch (same answer, slower).
"""

from __future__ import annotations

from importlib.resources import files

import cedarpy

from memgate.residual import Compiler, Unsupported

from memgate.labels import LabelSet
from memgate.registry import Registry
from memgate.world import World

SCHEMA = files("memgate.policies").joinpath("memgate.cedarschema").read_text()
POLICIES = files("memgate.policies").joinpath("memgate.cedar").read_text()


def _uid(type_: str, id_: str) -> dict:
    return {"__entity": {"type": type_, "id": id_}}


def _ref(type_: str, id_: str) -> str:
    return f'{type_}::"{id_}"'


class Policy:
    def __init__(self, world: World, registry: Registry, policies: str = POLICIES, schema: str = SCHEMA):
        self.world, self.registry, self.policies, self.schema = world, registry, policies, schema
        # (agent, location) -> (world fingerprint, compiled filter, allowed IDs, newest registry row seen)
        self._cache: dict[tuple[str, str], tuple] = {}

    def _known(self, agent: str, location: str, w: World | None = None) -> bool:
        """Fail closed: decide nothing about an agent or location the world doesn't list.

        Cedar skips a policy whose evaluation errors, and a skipped forbid allows. A location missing
        from the world has no entity, so the high-assurance write seal would error and be skipped.
        The proofs assume every agent and location in a request exists; this makes that true."""
        w = self.world if w is None else w
        return agent in w.agents and location in w.locations

    def validate(self) -> list[str]:
        result = cedarpy.validate_policies(self.policies, self.schema)
        return [str(e) for e in result.errors]

    def _label_set_entity(self, id_: str, ls: LabelSet, w: World | None = None) -> dict:
        w = self.world if w is None else w
        return {
            "uid": {"type": "LabelSet", "id": id_},
            "attrs": {
                "selfs": [_uid("Agent", a) for a in sorted(ls.selfs)],
                "locs": [_uid("Location", l) for l in sorted(ls.locs)],
                "withs": [_uid("Agent", a) for a in sorted(ls.withs)],
                "haLocs": [_uid("Location", l) for l in sorted(ls.locs) if w.high_assurance(l)],
                "carryTypes": sorted(w.carry_out_types(ls.locs)),
                "srcs": [_uid("Location", l) for l in sorted(ls.srcs)],
                "sealedSrcs": [_uid("Location", l) for l in sorted(ls.srcs) if w.sealed(l)],
            },
            "parents": [],
        }

    def _entities(self, label_sets: dict[str, LabelSet], w: World | None = None) -> list[dict]:
        w = self.world if w is None else w
        agents = set(w.agents) | {a for ls in label_sets.values() for a in ls.selfs | ls.withs}
        # A source location the world no longer lists still names an entity, so the policies never error on it.
        extra_locs = {l for ls in label_sets.values() for l in ls.srcs} - set(w.locations)
        ents = [{"uid": {"type": "Agent", "id": a}, "attrs": {}, "parents": []} for a in sorted(agents)]
        ents += [{"uid": {"type": "Environment", "id": e}, "attrs": {}, "parents": []} for e in sorted(w.environments)]
        ents += [{"uid": {"type": "Location", "id": l.id},
                  "attrs": {"highAssurance": l.high_assurance, "environment": _uid("Environment", l.environment)},
                  "parents": []} for l in w.locations.values()]
        if extra_locs:
            ents.append({"uid": {"type": "Environment", "id": "∅"}, "attrs": {}, "parents": []})
            ents += [{"uid": {"type": "Location", "id": l}, "attrs": {"highAssurance": False, "environment": _uid("Environment", "∅")},
                      "parents": []} for l in sorted(extra_locs)]
        ents += [self._label_set_entity(i, ls, w) for i, ls in label_sets.items()]
        return ents

    def _residual_where(self, agent: str, location: str, w: World | None = None) -> tuple[str, list]:
        w = self.world if w is None else w
        request = {"principal": _ref("Agent", agent), "action": _ref("Action", "read"), "resource": None,
                   "context": {"location": _uid("Location", location)}}
        result = cedarpy.is_authorized_partial(request, self.policies, self._entities({}, w), self.schema)
        if result.diagnostics.errors:
            raise Unsupported("partial evaluation reported errors")
        if result.decision == cedarpy.Decision.Allow:      # decided without looking at the label set
            return "TRUE", []
        if result.decision == cedarpy.Decision.Deny:
            return "FALSE", []
        return Compiler(w).where(result.residuals)

    def allowed_ids(self, agent: str, location: str) -> set[str]:
        """Label sets `agent` may read at `location`, via the compiled residual (exact fallback).

        Cached per (agent, location): the registry only grows, so a repeat call checks only label sets
        registered since the last one. A change to the world invalidates the cache."""
        w = self.world                                     # one world for the whole decision
        if not self._known(agent, location, w):
            return set()
        key, fp = (agent, location), w.fingerprint()
        cached = self._cache.get(key)
        if cached and cached[0] == fp:
            _, where, params, allowed, newest = cached
        else:
            try:
                where, params = self._residual_where(agent, location, w)
            except Unsupported:
                return self.allowed_ids_exact(agent, location, w)
            allowed, newest = set(), 0
        new, newest = self.registry.select_ids(where, params, after=newest)
        allowed = allowed | new
        self._cache[key] = (fp, where, params, allowed, newest)
        return set(allowed)

    def allowed_ids_exact(self, agent: str, location: str, w: World | None = None) -> set[str]:
        """Check every registered label set with Cedar (the reference answer)."""
        w = self.world if w is None else w
        if not self._known(agent, location, w):
            return set()
        label_sets = self.registry.all()
        if not label_sets:
            return set()
        requests = [{"principal": _ref("Agent", agent), "action": _ref("Action", "read"),
                     "resource": _ref("LabelSet", i), "context": {"location": _uid("Location", location)}}
                    for i in label_sets]
        results = cedarpy.is_authorized_batch(requests, self.policies, self._entities(label_sets, w), self.schema)
        return {i for i, r in zip(label_sets, results) if r.allowed}

    def may_write(self, agent: str, location: str, labels: LabelSet, world: World | None = None) -> bool:
        """May `agent`, at `location`, store a memory under `labels`? Decided with `world` when given (the caller's
        snapshot, so the decision and the write's routing see the same world), else the current one."""
        w = self.world if world is None else world
        if not self._known(agent, location, w):
            return False
        request = {"principal": _ref("Agent", agent), "action": _ref("Action", "write"),
                   "resource": _ref("LabelSet", labels.id), "context": {"location": _uid("Location", location)}}
        return cedarpy.is_authorized(request, self.policies, self._entities({labels.id: labels}, w), self.schema).allowed

    def may_carry_out(self, agent: str, location: str, source: LabelSet, memory_type: str, world: World | None = None) -> bool:
        """May `agent`, at `location`, carry a `memory_type` formed under `source` into personal memory?"""
        w = self.world if world is None else world
        if not self._known(agent, location, w):
            return False
        request = {"principal": _ref("Agent", agent), "action": _ref("Action", "writePersonal"),
                   "resource": _ref("LabelSet", source.id),
                   "context": {"memoryType": memory_type, "location": _uid("Location", location)}}
        return cedarpy.is_authorized(request, self.policies, self._entities({source.id: source}, w), self.schema).allowed
