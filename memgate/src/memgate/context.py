"""A memgate deployment (`Gate`: the world, the registry, the secret) and the `Context` each call is
decided on.

Both sides of an adapter (the memgate client and, for Hindsight, the validator running inside the
memory system) load the same files, so they decide identically.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dataclasses import dataclass

from memgate.derivation import conversation_labels
from memgate.labels import LabelSet
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World

HEADER_AGENT = "x-memgate-agent"
HEADER_LOCATION = "x-memgate-location"
HEADER_SECRET = "x-memgate-secret"
HEADER_ROLE = "x-memgate-role"          # "agent" (default) or "admin"
HEADERS = (HEADER_AGENT, HEADER_LOCATION, HEADER_SECRET, HEADER_ROLE)

@dataclass(frozen=True)
class Context:
    """Who is acting, where, and who else is present: everything memgate decides a call on.

    memgate trusts a Context as given. The host builds it from what it has verified (the agent's
    identity, where the agent is, who is with it); an agent must never supply its own. See the
    integration guide (memgate/INTEGRATION.md) for the contract.
    """
    agent: str
    location: str
    participants: tuple[str, ...] = ()     # everyone present; the agent is always included

    def __post_init__(self) -> None:
        object.__setattr__(self, "participants", tuple(sorted(set(self.participants) | {self.agent})))

    def conversation(self) -> LabelSet:
        """The label set of what is said here, among these participants."""
        return conversation_labels(self.location, self.participants)


# Each high-assurance location gets its own partition (a separate bank in the memory system), so its
# memories never share ranking statistics, caches or consolidation with anything outside it.
PARTITION_SEP = "--ha--"


def partition_bank(bank: str, location: str) -> str:
    """The partition (bank) holding high-assurance location `location`'s memories."""
    return f"{bank}{PARTITION_SEP}{location}"


def partition_location(bank: str, world: World) -> str | None:
    """The high-assurance location a bank is the partition of, or None for a shared bank."""
    if PARTITION_SEP not in bank:
        return None
    loc = bank.rsplit(PARTITION_SEP, 1)[1]
    return loc if loc in world.locations and world.high_assurance(loc) else None


def load_world(path: str | Path) -> World:
    spec = json.loads(Path(path).read_text())
    w = World()
    for e in spec["environments"]:
        w.add_environment(e["id"], carry_out=e.get("carry_out", ("fact", "opinion", "skill", "episode")))
    for l in spec["locations"]:
        w.add_location(l["id"], l["environment"], l.get("high_assurance", False))
    w.add_agents(*spec.get("agents", []))
    return w


class Gate:
    """The world, the registry and the secret one memgate deployment decides with.

    Given `world_path`, the gate follows the world file: at most once every `check_every` seconds it
    looks at the file's modification time and size, and reloads it when they change, so a running
    simulation can add agents, locations or environments without restarting anything. The policy's
    decision cache is keyed on the world's fingerprint, so a reload invalidates it. A file that
    doesn't parse (e.g. caught mid-write) is ignored and the last good world stays in force; write
    the file atomically (to a temporary name, then rename) to avoid that window.
    """

    def __init__(self, world: World, registry: Registry, secret: str, world_path: str | Path | None = None,
                 check_every: float = 1.0):
        self._world, self.registry, self.secret = world, registry, secret
        self.world_path = Path(world_path) if world_path else None
        self.check_every = check_every
        self._stamp = self._file_stamp()
        self._checked = time.monotonic()
        self._policy = Policy(world, registry)            # one instance, so its decision cache survives
        self.reload_errors = 0

    def _file_stamp(self) -> tuple | None:
        if not self.world_path:
            return None
        try:
            st = self.world_path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def refresh(self, force: bool = False) -> bool:
        """Reload the world file if it changed; returns True if a new world took effect."""
        if not self.world_path or (not force and time.monotonic() - self._checked < self.check_every):
            return False
        self._checked = time.monotonic()
        stamp = self._file_stamp()
        if stamp is None or stamp == self._stamp:
            return False
        try:
            world = load_world(self.world_path)
        except (ValueError, KeyError, OSError):
            self.reload_errors += 1                        # keep deciding with the last good world
            return False
        self._stamp, self._world = stamp, world
        self._policy.world = world
        return True

    @property
    def world(self) -> World:
        self.refresh()
        return self._world

    @property
    def policy(self) -> Policy:
        self.refresh()
        return self._policy

    @classmethod
    def from_env(cls, prefix: str = "MEMGATE") -> "Gate":
        """From MEMGATE_WORLD, MEMGATE_REGISTRY and MEMGATE_SECRET; MEMGATE_WORLD_CHECK_S sets how often
        (in seconds, default 1; 0 means on every decision) the world file is checked for changes."""
        path = os.environ[f"{prefix}_WORLD"]
        return cls(load_world(path), Registry(os.environ[f"{prefix}_REGISTRY"]), os.environ[f"{prefix}_SECRET"],
                   world_path=path, check_every=float(os.environ.get(f"{prefix}_WORLD_CHECK_S", "1.0")))
