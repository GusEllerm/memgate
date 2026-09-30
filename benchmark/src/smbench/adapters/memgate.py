"""memgate adapter: LoCoMo with labels on, through memgate and a gated Hindsight (see
memgate/scripts/serve_hindsight_gated.sh).

All ten conversations share one bank (SMBENCH_BANK), so memgate has something to lock. Each
conversation happens at its own location between its two speakers: every session is labelled with
that location and pair, and each question is asked by the first speaker at that location. memgate
must hide the other nine conversations while keeping this one fully readable, so any drop against
the isolated-bank Hindsight run is the recall cost of filtering.

`memgate-nofilter` searches the same shared bank with no filter (the validator's internal role), to
show what the filter prevents: other conversations' memories, including same-named speakers.

The gate's world must list the LoCoMo agents and locations: `python -m smbench.adapters.memgate
--add-to-world <world.json>`, then restart the gated server.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path

from smbench.adapters import Memory, Session

ENVIRONMENT = "locomo"


def agent_id(conversation_id: str, speaker: str) -> str:
    return f"{conversation_id}-{speaker}"


def location_id(conversation_id: str) -> str:
    return f"{ENVIRONMENT}-{conversation_id}"


class MemgateAdapter:
    name = "memgate"

    def __init__(self, run_id: str, base_url: str | None = None, filtered: bool = True):
        from memgate.adapters.hindsight.client import HindsightMemory
        from memgate.context import Gate
        self.base_url = base_url or os.environ.get("MEMGATE_HINDSIGHT_URL", "http://127.0.0.1:8890")
        self.bank = os.environ.get("SMBENCH_BANK") or f"{run_id}-shared"
        self.filtered = filtered
        self.name = "memgate" if filtered else "memgate-nofilter"
        self.mem = HindsightMemory(Gate.from_env(), bank=self.bank, base_url=self.base_url)
        self._speakers: dict[str, tuple[str, str]] = {}
        self._created = False
        self._lock = threading.Lock()

    def _ensure_bank(self) -> None:
        with self._lock:
            if not self._created:
                self.mem.create_bank()       # PUT: a no-op if another process already made it
                self._created = True

    def _asker(self, conversation_id: str) -> str:
        if conversation_id not in self._speakers:
            from smbench.locomo import data
            conv = next(s for s in data.load() if s["sample_id"] == conversation_id)["conversation"]
            self._speakers[conversation_id] = (conv["speaker_a"], conv["speaker_b"])
        return agent_id(conversation_id, self._speakers[conversation_id][0])

    def ingest_session(self, session: Session) -> None:
        self._ensure_bank()
        cid = session.conversation_id
        self._speakers[cid] = session.speakers
        participants = [agent_id(cid, s) for s in session.speakers]
        from memgate import Context
        self.mem.remember(Context(participants[0], location_id(cid), tuple(participants)), session.transcript(),
                          when=session.when, about=f"Conversation between {session.speakers[0]} and {session.speakers[1]}")

    def finalize(self, conversation_id: str) -> None:
        # The bank is shared, so this also waits for other conversations' background work.
        self._ensure_bank()
        while self.mem.pending_operations():
            time.sleep(5)

    def search(self, conversation_id: str, query: str, k: int) -> list[Memory]:
        if self.filtered:
            from memgate import Context
            hits = self.mem.recall(Context(self._asker(conversation_id), location_id(conversation_id)), query, k=k)
            return [Memory(text=h.text, when=h.when) for h in hits]
        resp = self.mem._call("POST", f"/v1/default/banks/{self.bank}/memories/recall",
                              {"query": query, "budget": "mid"}, role="internal")
        out = []
        for r in resp.get("results", [])[:k]:
            when = r.get("occurred_start") or r.get("mentioned_at")
            out.append(Memory(text=r["text"], when=str(when)[:10] if when else None))
        return out

    def describe(self) -> dict:
        import importlib.metadata
        return {"system": self.name, "hindsight_api": importlib.metadata.version("hindsight-api"),
                "memgate": importlib.metadata.version("memgate"), "bank": self.bank,
                "ingest": "one memgate remember per session (labels: the conversation's location and its two speakers), "
                          "all conversations in one shared bank; default observation consolidation",
                "search": ("memgate recall as the first speaker at the conversation's location" if self.filtered
                           else "unfiltered recall over the shared bank") + ", budget=mid, first k results"}


def add_to_world(path: Path) -> None:
    """Add the LoCoMo environment, one location per conversation, and every speaker to a gate world."""
    from smbench.locomo import data
    spec = json.loads(path.read_text())
    if not any(e["id"] == ENVIRONMENT for e in spec["environments"]):
        spec["environments"].append({"id": ENVIRONMENT, "carry_out": []})
    locs = {l["id"] for l in spec["locations"]}
    agents = set(spec.get("agents", []))
    for s in data.load():
        cid, conv = s["sample_id"], s["conversation"]
        if location_id(cid) not in locs:
            spec["locations"].append({"id": location_id(cid), "environment": ENVIRONMENT, "high_assurance": False})
        for sp in (conv["speaker_a"], conv["speaker_b"]):
            if agent_id(cid, sp) not in agents:
                spec.setdefault("agents", []).append(agent_id(cid, sp))
    path.write_text(json.dumps(spec, indent=1))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--add-to-world", type=Path, required=True)
    add_to_world(p.parse_args().add_to_world)
