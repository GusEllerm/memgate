"""Systems under test, all on Hindsight so the permission strategy is the only difference.

- nofilter:  one bank per world, every conversation stored, recall unfiltered (the leak baseline).
- peragent:  one bank per agent holding the conversations it witnessed; ignores location.
- memgate:   memgate's Hindsight client against a gated Hindsight (labels, allowed-ID filter, validator).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from smbench.selective.world import World

BASE = datetime(2026, 1, 5, 10, 0)


def transcript(world: World, conv) -> str:
    head = f"Conversation in the {conv.location.rstrip('0123456789')} between {', '.join(conv.participants)}."
    return "\n".join([head] + [f"{t['speaker']}: {t['text']}" for t in conv.turns])


def when(world: World, conv) -> datetime:
    return BASE + timedelta(days=world.conversations.index(conv))


class RawHindsight:
    """Minimal ungated Hindsight client (thread-safe; the official client runs its own event loop)."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(f"{self.base_url}{path}", method=method, headers={"Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=900) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}

    def bank(self, bank: str) -> None:
        self.call("PUT", f"/v1/default/banks/{bank}", {"name": bank})

    def retain(self, bank: str, text: str, ts: datetime, doc: str) -> None:
        self.call("POST", f"/v1/default/banks/{bank}/memories",
                  {"items": [{"content": text, "timestamp": ts.isoformat(), "document_id": doc}]})

    def recall(self, bank: str, query: str, k: int) -> list[str]:
        resp = self.call("POST", f"/v1/default/banks/{bank}/memories/recall", {"query": query, "budget": "mid"})
        return [r["text"] for r in resp.get("results", [])[:k]]

    def pending(self, bank: str) -> int:
        ops = self.call("GET", f"/v1/default/banks/{bank}/operations")
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        return sum(o.get("status") not in ("completed", "failed", "cancelled") for o in ops)


class NoFilter:
    name = "nofilter"

    def __init__(self, url: str, run: str):
        self.h, self.run = RawHindsight(url), run

    def _bank(self, world: World) -> str:
        return f"{self.run}-nofilter-w{world.seed}"

    def ingest_jobs(self, world: World) -> list:
        """Create the banks, then return one zero-argument job per store (run in parallel by the runner)."""
        self.h.bank(self._bank(world))
        return [lambda c=c: self.h.retain(self._bank(world), transcript(world, c), when(world, c), c.id)
                for c in world.conversations]

    def banks(self, world: World) -> list[str]:
        return [self._bank(world)]

    def pending(self, world: World) -> int:
        return sum(self.h.pending(b) for b in self.banks(world))

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        return self.h.recall(self._bank(world), query, k)


class PerAgent(NoFilter):
    name = "peragent"

    def _agent_bank(self, world: World, agent: str) -> str:
        return f"{self.run}-peragent-{agent}"

    def ingest_jobs(self, world: World) -> list:
        for a in world.agents:
            self.h.bank(self._agent_bank(world, a))
        return [lambda c=c, a=a: self.h.retain(self._agent_bank(world, a), transcript(world, c), when(world, c), f"{c.id}-{a}")
                for c in world.conversations for a in c.participants]

    def banks(self, world: World) -> list[str]:
        return [self._agent_bank(world, a) for a in world.agents]

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        return self.h.recall(self._agent_bank(world, agent), query, k)


class Memgate:
    name = "memgate"

    def __init__(self, url: str, run: str, gate):
        from memgate.adapters.hindsight.client import HindsightMemory
        self.gate, self.run, self.url, self._mem = gate, run, url, {}
        self._cls = HindsightMemory

    def _m(self, world: World):
        if world.seed not in self._mem:
            self._mem[world.seed] = self._cls(self.gate, bank=f"{self.run}-memgate-w{world.seed}", base_url=self.url)
        return self._mem[world.seed]

    def ingest_jobs(self, world: World) -> list:
        m = self._m(world)
        m.create_bank()
        return [lambda c=c: m.remember(c.participants[0], c.location, c.participants, transcript(world, c), when=when(world, c))
                for c in world.conversations]

    def pending(self, world: World) -> int:
        return self._m(world).pending_operations()

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        return [r.text for r in self._m(world).recall(agent, location, query, k=k)]


def wait(system, world: World, timeout: float = 1800) -> None:
    deadline = time.time() + timeout
    while system.pending(world) and time.time() < deadline:
        time.sleep(5)
