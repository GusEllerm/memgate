"""The world the policies reason about: environments, their locations, and the agents in them.

An environment decides which memory types may be carried out of its locations into an agent's
personal memory: all of them (open), some (selective, e.g. opinions but not facts), or none
(Severance). High-assurance locations never let anything out, whatever their environment says.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MEMORY_TYPES = frozenset({"fact", "opinion", "skill", "episode"})


@dataclass(frozen=True)
class Environment:
    id: str
    carry_out: frozenset[str] = MEMORY_TYPES  # empty = Severance


@dataclass(frozen=True)
class Location:
    id: str
    environment: str
    high_assurance: bool = False


@dataclass
class World:
    environments: dict[str, Environment] = field(default_factory=dict)
    locations: dict[str, Location] = field(default_factory=dict)
    agents: set[str] = field(default_factory=set)

    def add_environment(self, id: str, carry_out=MEMORY_TYPES) -> Environment:
        env = Environment(id, frozenset(carry_out))
        self.environments[id] = env
        return env

    def add_location(self, id: str, environment: str, high_assurance: bool = False) -> Location:
        if environment not in self.environments:
            raise KeyError(f"unknown environment {environment!r}")
        loc = Location(id, environment, high_assurance)
        self.locations[id] = loc
        return loc

    def add_agents(self, *ids: str) -> None:
        self.agents.update(ids)

    def high_assurance(self, loc: str) -> bool:
        return self.locations[loc].high_assurance

    def carry_out_types(self, locs: frozenset[str]) -> frozenset[str]:
        """Memory types every one of these locations lets out; all types when there are none."""
        allowed = MEMORY_TYPES
        for loc in locs:
            allowed = allowed & self.environments[self.locations[loc].environment].carry_out
        return allowed
