"""The world the policies reason about: environments, their locations, and the agents in them.

An environment decides which memory types may be carried out of its locations into an agent's
personal memory: all of them (open), some (selective, e.g. opinions but not facts), or none
(Severance). High-assurance locations never let anything out, whatever their environment says.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from memgate.labels import class_rank, strictest

MEMORY_TYPES = frozenset({"fact", "opinion", "skill", "episode"})


@dataclass(frozen=True)
class Environment:
    id: str
    carry_out: frozenset[str] = MEMORY_TYPES  # empty = Severance
    min_class: str | None = None              # since 0.5.0: carry-outs from here need at least this class


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

    def add_environment(self, id: str, carry_out=MEMORY_TYPES, min_class: str | None = None) -> Environment:
        class_rank(min_class)                          # raises for an unknown class
        env = Environment(id, frozenset(carry_out), min_class)
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

    def fingerprint(self) -> tuple:
        """Changes whenever anything the policies read changes (for caching decisions)."""
        return (tuple(sorted((e.id, tuple(sorted(e.carry_out)), e.min_class or "") for e in self.environments.values())),
                tuple(sorted((l.id, l.environment, l.high_assurance) for l in self.locations.values())),
                tuple(sorted(self.agents)))

    def high_assurance(self, loc: str) -> bool:
        return self.locations[loc].high_assurance

    def carry_out_types(self, locs: frozenset[str]) -> frozenset[str]:
        """Memory types every one of these locations lets out; all types when there are none."""
        allowed = MEMORY_TYPES
        for loc in locs:
            allowed = allowed & self.environments[self.locations[loc].environment].carry_out
        return allowed

    def min_class(self, locs) -> str | None:
        """The strictest minimum class among these locations' environments (None if none sets one).
        A host bug guard, never a source of the class: memgate does not choose a carry-out's class."""
        return strictest({self.environments[self.locations[l].environment].min_class
                          for l in locs if l in self.locations} - {None})
