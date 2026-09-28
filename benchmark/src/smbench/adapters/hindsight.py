"""Hindsight adapter: talks to a running hindsight-api server (see scripts/serve_hindsight.sh)."""

from __future__ import annotations

import importlib.metadata
import json
import os
import threading
import time
import urllib.request

from hindsight_client import Hindsight

from smbench.adapters import Memory, Session


class HindsightAdapter:
    name = "hindsight"

    def __init__(self, run_id: str, base_url: str | None = None):
        self.base_url = base_url or os.environ.get("HINDSIGHT_URL", "http://127.0.0.1:8888")
        self._local = threading.local()
        self.run_id = run_id
        self._banks: set[str] = set()
        self._bank_lock = threading.Lock()

    @property
    def client(self) -> Hindsight:
        # The client drives its own event loop, so each worker thread needs its own instance.
        if not hasattr(self._local, "client"):
            self._local.client = Hindsight(base_url=self.base_url, timeout=900)
        return self._local.client

    def _bank(self, conversation_id: str) -> str:
        bank = f"{self.run_id}-{conversation_id}"
        if bank not in self._banks:
            with self._bank_lock:
                if bank not in self._banks:
                    self.client.create_bank(bank_id=bank, name=bank)
                    self._banks.add(bank)
        return bank

    def ingest_session(self, session: Session) -> None:
        self.client.retain(
            bank_id=self._bank(session.conversation_id),
            content=session.transcript(),
            timestamp=session.when,
            context=f"Conversation between {session.speakers[0]} and {session.speakers[1]}",
            document_id=f"{session.conversation_id}-s{session.index}",
        )

    def _operations(self, bank: str) -> list[dict]:
        with urllib.request.urlopen(f"{self.base_url}/v1/default/banks/{bank}/operations", timeout=60) as r:
            data = json.loads(r.read())
        return data.get("operations", data if isinstance(data, list) else [])

    def finalize(self, conversation_id: str) -> None:
        bank = self._bank(conversation_id)
        while True:
            # Hindsight reports "pending" and "processing"; anything not finished counts as pending.
            pending = [o for o in self._operations(bank) if o.get("status") not in ("completed", "failed", "cancelled")]
            if not pending:
                return
            time.sleep(5)

    def search(self, conversation_id: str, query: str, k: int) -> list[Memory]:
        resp = self.client.recall(bank_id=self._bank(conversation_id), query=query, budget="mid")
        out = []
        for r in resp.results[:k]:
            when = r.occurred_start or r.mentioned_at
            out.append(Memory(text=r.text, when=str(when)[:10] if when else None))
        return out

    def describe(self) -> dict:
        return {"system": "hindsight", "hindsight_api": importlib.metadata.version("hindsight-api"),
                "hindsight_client": importlib.metadata.version("hindsight-client"),
                "ingest": "one retain per session transcript, synchronous; default observation consolidation",
                "search": "recall budget=mid, first k results"}
