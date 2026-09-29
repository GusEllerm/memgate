"""Cedar decisions over label sets.

`allowed_ids` answers "which label sets may this agent read here?" by checking every registered
label set in one Cedar batch. That is exact and fast enough at simulation scale (thousands of label
sets). At larger scale, Cedar's partial evaluation gives a residual condition that can be compiled
into a query over the registry instead (docs/vault/Reference/Cedar.md); the answer is the same.
"""

from __future__ import annotations

from importlib.resources import files

import cedarpy

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

    def validate(self) -> list[str]:
        result = cedarpy.validate_policies(self.policies, self.schema)
        return [str(e) for e in result.errors]

    def _label_set_entity(self, id_: str, ls: LabelSet) -> dict:
        return {
            "uid": {"type": "LabelSet", "id": id_},
            "attrs": {
                "selfs": [_uid("Agent", a) for a in sorted(ls.selfs)],
                "locs": [_uid("Location", l) for l in sorted(ls.locs)],
                "withs": [_uid("Agent", a) for a in sorted(ls.withs)],
                "haLocs": [_uid("Location", l) for l in sorted(ls.locs) if self.world.high_assurance(l)],
                "carryTypes": sorted(self.world.carry_out_types(ls.locs)),
            },
            "parents": [],
        }

    def _entities(self, label_sets: dict[str, LabelSet]) -> list[dict]:
        w = self.world
        agents = set(w.agents) | {a for ls in label_sets.values() for a in ls.selfs | ls.withs}
        ents = [{"uid": {"type": "Agent", "id": a}, "attrs": {}, "parents": []} for a in sorted(agents)]
        ents += [{"uid": {"type": "Environment", "id": e}, "attrs": {}, "parents": []} for e in sorted(w.environments)]
        ents += [{"uid": {"type": "Location", "id": l.id},
                  "attrs": {"highAssurance": l.high_assurance, "environment": _uid("Environment", l.environment)},
                  "parents": []} for l in w.locations.values()]
        ents += [self._label_set_entity(i, ls) for i, ls in label_sets.items()]
        return ents

    def allowed_ids(self, agent: str, location: str) -> set[str]:
        label_sets = self.registry.all()
        if not label_sets:
            return set()
        requests = [{"principal": _ref("Agent", agent), "action": _ref("Action", "read"),
                     "resource": _ref("LabelSet", i), "context": {"location": _uid("Location", location)}}
                    for i in label_sets]
        results = cedarpy.is_authorized_batch(requests, self.policies, self._entities(label_sets), self.schema)
        return {i for i, r in zip(label_sets, results) if r.allowed}

    def may_carry_out(self, agent: str, source: LabelSet, memory_type: str) -> bool:
        request = {"principal": _ref("Agent", agent), "action": _ref("Action", "writePersonal"),
                   "resource": _ref("LabelSet", source.id), "context": {"memoryType": memory_type}}
        return cedarpy.is_authorized(request, self.policies, self._entities({source.id: source}), self.schema).allowed
