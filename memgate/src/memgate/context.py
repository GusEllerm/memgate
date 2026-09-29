"""Shared setup for a memgate deployment: where the world and the registry live, and the gate secret.

Both sides of an adapter (the memgate client and, for Hindsight, the validator running inside the
memory system) load the same files, so they decide identically.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World

HEADER_AGENT = "x-memgate-agent"
HEADER_LOCATION = "x-memgate-location"
HEADER_SECRET = "x-memgate-secret"
HEADER_ROLE = "x-memgate-role"          # "agent" (default) or "admin"
HEADERS = (HEADER_AGENT, HEADER_LOCATION, HEADER_SECRET, HEADER_ROLE)


def load_world(path: str | Path) -> World:
    spec = json.loads(Path(path).read_text())
    w = World()
    for e in spec["environments"]:
        w.add_environment(e["id"], carry_out=e.get("carry_out", ("fact", "opinion", "skill", "episode")))
    for l in spec["locations"]:
        w.add_location(l["id"], l["environment"], l.get("high_assurance", False))
    w.add_agents(*spec.get("agents", []))
    return w


@dataclass
class Gate:
    world: World
    registry: Registry
    secret: str

    def __post_init__(self) -> None:
        self._policy = Policy(self.world, self.registry)   # one instance, so its decision cache survives

    @property
    def policy(self) -> Policy:
        return self._policy

    @classmethod
    def from_env(cls, prefix: str = "MEMGATE") -> "Gate":
        return cls(load_world(os.environ[f"{prefix}_WORLD"]), Registry(os.environ[f"{prefix}_REGISTRY"]),
                   os.environ[f"{prefix}_SECRET"])
