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


def personal_text(world: World, agent: str, fact_id: str) -> str:
    """What an agent writes into its personal memory when it carries a fact or opinion out (S4/S5)."""
    return f"{agent}'s personal memory: {world.facts[fact_id].sentence}"


def note_text(world: World, note: dict) -> str:
    place = note["location"].rstrip("0123456789")
    return f"{note['agent']}'s private note, kept in the {place}: {world.facts[note['fact']].sentence}"


def extras(world: World) -> list[tuple[str, str, str, datetime, str]]:
    """(kind, agent, text, time, key) for every carry-out attempt and note in the world."""
    out = []
    for c in world.conversations:
        for co in c.carry_outs:
            out.append(("carry", co["agent"], personal_text(world, co["agent"], co["fact"]),
                        when(world, c) + timedelta(hours=1), f"{c.id}-carry-{co['fact']}"))
    for i, n in enumerate(world.notes):
        out.append(("note", n["agent"], note_text(world, n), BASE + timedelta(days=len(world.conversations) + i), f"note-{n['fact']}"))
    return out


STAT_FIELDS = ("total_nodes", "total_links", "total_documents", "total_observations", "last_memory_write_at")


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

    def snapshot(self, bank: str) -> dict:
        st = self.call("GET", f"/v1/default/banks/{bank}/stats")
        ops = self.call("GET", f"/v1/default/banks/{bank}/operations")
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        return {**{k: st.get(k) for k in STAT_FIELDS}, "operations": len(ops)}


class NoFilter:
    name = "nofilter"

    def __init__(self, url: str, run: str):
        self.h, self.run = RawHindsight(url), run

    def _bank(self, world: World) -> str:
        return f"{self.run}-nofilter-w{world.seed}"

    def ingest_jobs(self, world: World) -> list:
        """Create the banks, then return one zero-argument job per store (run in parallel by the runner)."""
        self.h.bank(self._bank(world))
        jobs = [lambda c=c: self.h.retain(self._bank(world), transcript(world, c), when(world, c), c.id)
                for c in world.conversations]
        # No permission check: every carry-out attempt and note is simply stored.
        jobs += [lambda e=e: self.h.retain(self._bank(world), e[2], e[3], e[4]) for e in extras(world)]
        return jobs

    def banks(self, world: World) -> list[str]:
        return [self._bank(world)]

    def pending(self, world: World) -> int:
        return sum(self.h.pending(b) for b in self.banks(world))

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        return self.h.recall(self._bank(world), query, k)

    def snapshot(self, world: World) -> dict:
        return {b: self.h.snapshot(b) for b in self.banks(world)}


class PerAgent(NoFilter):
    name = "peragent"

    def _agent_bank(self, world: World, agent: str) -> str:
        return f"{self.run}-peragent-{agent}"

    def ingest_jobs(self, world: World) -> list:
        for a in world.agents:
            self.h.bank(self._agent_bank(world, a))
        jobs = [lambda c=c, a=a: self.h.retain(self._agent_bank(world, a), transcript(world, c), when(world, c), f"{c.id}-{a}")
                for c in world.conversations for a in c.participants]
        # No permission check: carry-outs and notes go into the agent's own bank.
        jobs += [lambda e=e: self.h.retain(self._agent_bank(world, e[1]), e[2], e[3], e[4]) for e in extras(world)]
        return jobs

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
        from memgate import Context
        m = self._m(world)
        m.create_bank()
        jobs = [lambda c=c: m.remember(Context(c.participants[0], c.location, tuple(c.participants)), transcript(world, c),
                                       when=when(world, c))
                for c in world.conversations]
        self.refused: dict[int, list[str]] = getattr(self, "refused", {})   # world seed -> refused facts
        refused = self.refused.setdefault(world.seed, [])

        def carry(c, co):
            try:
                m.carry_out(Context(co["agent"], c.location, tuple(c.participants)),   # source: this conversation
                            personal_text(world, co["agent"], co["fact"]), world.facts[co["fact"]].kind,
                            when=when(world, c))
            except PermissionError:
                refused.append(co["fact"])                 # memgate refused it: nothing is stored

        jobs += [lambda c=c, co=co: carry(c, co) for c in world.conversations for co in c.carry_outs]
        jobs += [lambda n=n: m.keep_note(Context(n["agent"], n["location"]), note_text(world, n)) for n in world.notes]
        return jobs

    def pending(self, world: World) -> int:
        return self._m(world).pending_operations()

    def recall(self, world: World, agent: str, location: str, query: str, k: int) -> list[str]:
        from memgate import Context
        return [r.text for r in self._m(world).recall(Context(agent, location), query, k=k)]

    def snapshot(self, world: World) -> dict:
        """Stats for the shared bank and every high-assurance partition that exists."""
        from memgate.adapters.hindsight.client import HindsightError
        m = self._m(world)
        out = {}
        for bank in m.partitions():
            try:
                st = m._call("GET", f"/v1/default/banks/{bank}/stats", None, role="admin")
                ops = m._call("GET", f"/v1/default/banks/{bank}/operations", None, role="admin")
            except HindsightError as e:
                if e.status == 404:
                    continue
                raise
            ops = ops.get("operations", ops if isinstance(ops, list) else [])
            out[bank] = {**{k: st.get(k) for k in STAT_FIELDS}, "operations": len(ops)}
        return out


def wait(system, world: World, timeout: float = 1800) -> None:
    deadline = time.time() + timeout
    while system.pending(world) and time.time() < deadline:
        time.sleep(5)
