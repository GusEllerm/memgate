"""The selective benchmark's systems on Mem0 (open source, in process) instead of Hindsight.

Needs the mem0 environment (`.venvs/mem0`, which also has memgate):

    PYTHONPATH=src .venvs/mem0/bin/python -m smbench.selective.run --run sel-env-mem0-2026-10-01 --size env \\
        --seeds 21 22 23 --systems mem0-nofilter mem0-peragent mem0-memgate

Mem0 scopes everything by `user_id`: on add() it retrieves the existing memories in that scope and has the
LLM decide what to add, update or delete against them; search() filters by scope. The three systems
differ only in what they use as the scope:

- mem0-nofilter: one scope per world (the leak baseline);
- mem0-peragent: one scope per agent, holding what it witnessed (location ignored);
- mem0-memgate: one scope per label set. memgate decides the labels and the permissions (its client-side
  lock; Mem0 has no validator hook, so there is no second lock). Because add() only looks at memories in
  the same scope, Mem0 never merges or updates across label sets: label-safe compaction by construction.
  Recall searches once with an OR filter over the label sets the agent may read here (ANDed with a constant
  agent_id, which Mem0 requires as a top-level scope key).

Mem0's own `add(infer=True)` extraction runs on every write, through the ALCF gateway, like Hindsight's.
"""

from __future__ import annotations

import importlib.metadata
import os
import threading
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MEM0_TELEMETRY", "false")

from smbench.adapters import EMBEDDER  # noqa: E402
from smbench.selective.systems import note_text, personal_text, transcript, when  # noqa: E402
from smbench.selective.world import World  # noqa: E402

GATEWAY = "http://127.0.0.1:8411/v1"
MODEL = "openai/gpt-oss-120b"
from memgate.adapters.mem0 import filters_for  # noqa: E402,F401  (memgate's Mem0 store; re-exported for the tests)
from memgate.adapters.mem0.store import TAG, Mem0Store as _MemgateMem0Store  # noqa: E402,F401

GATEWAY = "http://127.0.0.1:8411/v1"
MODEL = "openai/gpt-oss-120b"


class Mem0Store:
    """The benchmark's thin wrapper over memgate's Mem0 store: one Mem0 `Memory` per (run, system) on disk,
    the gateway as its LLM. `add`/`search` keep the benchmark's older call shape."""

    def __init__(self, run: str, name: str, root: Path = Path("results/mem0")):
        from memgate.context import Gate
        from memgate.registry import Registry
        from memgate.world import World
        gate = Gate(World(), Registry(), "benchmark")                 # the store itself makes no decisions
        self.inner = _MemgateMem0Store(gate, root / run / name, collection=name.replace("-", "_"),
                                       llm={"provider": "openai", "config": {"model": MODEL, "openai_base_url": GATEWAY,
                                                                              "api_key": "gateway", "temperature": 0.0,
                                                                              "max_tokens": 8000}})
        self.memory = self.inner.memory
        self._lock = self.inner._lock

    def add(self, scope: str, text: str, ts: datetime, **metadata) -> None:
        with self._lock:
            self.memory.add([{"role": "user", "content": text}], user_id=scope, agent_id=TAG,
                            metadata={"when": ts.isoformat(), **metadata})

    def search(self, scopes: list[str], query: str, k: int) -> list[str]:
        filters = filters_for(scopes)
        if filters is None:
            return []
        with self._lock:
            res = self.memory.search(query, top_k=k, filters=filters)
        return [r["memory"] for r in res.get("results", [])[:k]]

    @staticmethod
    def describe() -> dict:
        return {"mem0ai": importlib.metadata.version("mem0ai"), "embedder": EMBEDDER, "llm": MODEL, "llm_max_tokens": 8000}


class Mem0NoFilter:
    name = "mem0-nofilter"

    def __init__(self, run: str):
        self.run, self.store = run, Mem0Store(run, self.name)

    def scope(self, world: World, agent: str | None = None) -> str:
        return f"w{world.seed}"

    def ingest_jobs(self, world: World) -> list:
        jobs = [lambda c=c: self.store.add(self.scope(world, c.participants[0]), transcript(world, c), when(world, c),
                                           conversation=c.id, location=c.location)
                for c in world.conversations]
        # The baselines have no permission check: every attempted carry-out and note is stored.
        jobs += [lambda c=c, co=co: self.store.add(self.scope(world, co["agent"]), personal_text(world, co["agent"], co["fact"]),
                                                    when(world, c), carry_out=co["fact"])
                 for c in world.conversations for co in c.carry_outs]
        jobs += [lambda n=n: self.store.add(self.scope(world, n["agent"]), note_text(world, n), datetime(2026, 1, 1), note=n["fact"])
                 for n in world.notes]
        return jobs

    def pending(self, world: World) -> int:
        return 0                                      # Mem0's add() is synchronous

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        return self.store.search([self.scope(world, agent)], query, k)


class Mem0PerAgent(Mem0NoFilter):
    name = "mem0-peragent"

    def scope(self, world: World, agent: str | None = None) -> str:
        return f"w{world.seed}-{agent}"

    def ingest_jobs(self, world: World) -> list:
        jobs = [lambda c=c, a=a: self.store.add(self.scope(world, a), transcript(world, c), when(world, c),
                                                conversation=c.id, location=c.location)
                for c in world.conversations for a in c.participants]
        jobs += [lambda c=c, co=co: self.store.add(self.scope(world, co["agent"]), personal_text(world, co["agent"], co["fact"]),
                                                    when(world, c), carry_out=co["fact"])
                 for c in world.conversations for co in c.carry_outs]
        jobs += [lambda n=n: self.store.add(self.scope(world, n["agent"]), note_text(world, n), datetime(2026, 1, 1), note=n["fact"])
                 for n in world.notes]
        return jobs


class Mem0Memgate:
    """memgate's labels and permissions over Mem0: the label-set ID is Mem0's `user_id` scope."""
    name = "mem0-memgate"

    def __init__(self, run: str, gate):
        from memgate.provenance import write_id_for
        self.run, self.gate, self.store = run, gate, Mem0Store(run, self.name)
        self._write_id_for = write_id_for
        self.refused: dict[int, list[str]] = {}

    def _write(self, agent: str, location: str, labels, text: str, ts: datetime, **metadata) -> str:
        if not self.gate.policy.may_write(agent, location, labels):
            raise PermissionError(f"{agent} may not write {labels} at {location}")
        ls_id = self.gate.registry.register(labels)
        write_id = self._write_id_for(ls_id)
        self.store.add(ls_id, text, ts, label_set=ls_id, write_id=write_id, author=agent, location=location, **metadata)
        return write_id

    def ingest_jobs(self, world: World) -> list:
        from memgate.derivation import conversation_labels, personal_labels, personal_note_labels
        refused = self.refused.setdefault(world.seed, [])
        jobs = [lambda c=c: self._write(c.participants[0], c.location, conversation_labels(c.location, c.participants),
                                        transcript(world, c), when(world, c), conversation=c.id)
                for c in world.conversations]

        def carry(c, co):
            src = conversation_labels(c.location, c.participants)
            kind = world.facts[co["fact"]].kind
            if not self.gate.policy.may_carry_out(co["agent"], c.location, src, kind):
                refused.append(co["fact"])                      # refused: nothing is stored
                return
            self._write(co["agent"], c.location, personal_labels(co["agent"]), personal_text(world, co["agent"], co["fact"]),
                        when(world, c), carry_out=co["fact"], memory_type=kind)

        jobs += [lambda c=c, co=co: carry(c, co) for c in world.conversations for co in c.carry_outs]
        jobs += [lambda n=n: self._write(n["agent"], n["location"], personal_note_labels(n["agent"], n["location"]),
                                         note_text(world, n), datetime(2026, 1, 1), note=n["fact"])
                 for n in world.notes]
        return jobs

    def pending(self, world: World) -> int:
        return 0

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        allowed = sorted(self.gate.policy.allowed_ids(agent, location))
        return self.store.search(allowed, query, k)
