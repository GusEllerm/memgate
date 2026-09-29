"""memgate's Hindsight client: the only way agents' memory reaches Hindsight.

It labels every write from the context, registers the label set, and tags the item with its ID.
On recall it computes the allowed label sets itself (first lock) and passes them as tags; the
validator inside Hindsight recomputes and overwrites them (second lock). One Hindsight bank holds a
whole world; high-assurance locations can be given their own bank (a separate partition).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from memgate.context import HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, Gate
from memgate.derivation import conversation_labels, personal_labels, personal_note_labels
from memgate.labels import LabelSet


class HindsightError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        super().__init__(f"Hindsight {status}: {body[:300]}")


@dataclass
class Recalled:
    text: str
    label_set: str
    when: str | None


class HindsightMemory:
    def __init__(self, gate: Gate, bank: str, base_url: str = "http://127.0.0.1:8888", timeout: float = 900):
        self.gate, self.bank, self.base_url, self.timeout = gate, bank, base_url.rstrip("/"), timeout

    # -- transport ----------------------------------------------------------------------------------
    def _call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
              location: str | None = None, role: str = "agent") -> dict:
        headers = {"Content-Type": "application/json", HEADER_SECRET: self.gate.secret, HEADER_ROLE: role}
        if agent:
            headers[HEADER_AGENT] = agent
        if location:
            headers[HEADER_LOCATION] = location
        req = urllib.request.Request(f"{self.base_url}{path}", method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise HindsightError(e.code, e.read().decode(errors="replace")) from None

    def create_bank(self) -> None:
        self._call("PUT", f"/v1/default/banks/{self.bank}", {"name": self.bank}, role="admin")

    # -- writes -------------------------------------------------------------------------------------
    def _retain(self, agent: str, location: str, labels: LabelSet, text: str, when: datetime | None,
                context: str | None, document_id: str | None) -> str:
        ls_id = self.gate.registry.register(labels)
        item = {"content": text, "tags": [ls_id], "context": context, "document_id": document_id,
                "timestamp": when.isoformat() if when else None}
        self._call("POST", f"/v1/default/banks/{self.bank}/memories", {"items": [item]}, agent=agent, location=location)
        return ls_id

    def remember(self, agent: str, location: str, participants: list[str], text: str, *,
                 when: datetime | None = None, context: str | None = None, document_id: str | None = None) -> str:
        """Store something said or seen in a conversation at `location` among `participants`."""
        return self._retain(agent, location, conversation_labels(location, participants), text, when, context, document_id)

    def keep_note(self, agent: str, location: str, text: str, *, when: datetime | None = None) -> str:
        """A personal note that stays in `location` (e.g. inside a high-assurance location)."""
        return self._retain(agent, location, personal_note_labels(agent, location), text, when, "personal note", None)

    def carry_out(self, agent: str, location: str, source: LabelSet, text: str, memory_type: str, *,
                  when: datetime | None = None) -> str:
        """Copy something into the agent's personal memory, if every environment it came from allows."""
        if not self.gate.policy.may_carry_out(agent, source, memory_type):
            raise PermissionError(f"{memory_type} may not be carried out of {source}")
        return self._retain(agent, location, personal_labels(agent), text, when, f"carried out ({memory_type})", None)

    # -- reads --------------------------------------------------------------------------------------
    def recall(self, agent: str, location: str, query: str, k: int = 20, budget: str = "mid") -> list[Recalled]:
        allowed = sorted(self.gate.policy.allowed_ids(agent, location)) or ["ls_none"]
        resp = self._call("POST", f"/v1/default/banks/{self.bank}/memories/recall",
                          {"query": query, "budget": budget, "tags": allowed, "tags_match": "any_strict"},
                          agent=agent, location=location)
        out = []
        for r in resp.get("results", [])[:k]:
            tags = r.get("tags") or []
            when = r.get("occurred_start") or r.get("mentioned_at")
            out.append(Recalled(r["text"], tags[0] if tags else "", str(when)[:10] if when else None))
        return out

    def pending_operations(self) -> int:
        ops = self._call("GET", f"/v1/default/banks/{self.bank}/operations", None, role="admin")
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        return sum(o.get("status") not in ("completed", "failed", "cancelled") for o in ops)
