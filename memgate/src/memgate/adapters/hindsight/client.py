"""memgate's Hindsight clients: `Memory` and `AsyncMemory` (memgate.core) over the Hindsight store
(memgate.adapters.hindsight.store), under the names hosts already use.

    mem = HindsightMemory(gate, bank="ranch", base_url="unix:/srv/host/memgate-run/memgate.sock")

Every permission decision is made in memgate.core, which knows nothing about Hindsight; this module
only binds it to Hindsight's banks (partitions), tags (label sets) and document IDs (write IDs). The
validator inside Hindsight (memgate.adapters.hindsight.validator) is the second lock: it recomputes the
allowed label sets on every recall and checks every write, whatever the client sent.
"""

from __future__ import annotations

from memgate.context import Gate
from memgate.core import AsyncMemory, Memory, Recalled, RecallBatch   # noqa: F401  (re-exported)
from memgate.provenance import ProvenanceLog
from memgate.adapters.hindsight.store import (AsyncHindsightStore, HindsightError, HindsightStore, VersionMismatch,  # noqa: F401
                                               check_socket, send, socket_path)


class HindsightMemory(Memory):
    """Synchronous client (urllib, no dependencies). `bank` is the shared partition's name."""

    def __init__(self, gate: Gate, bank: str, base_url: str = "http://127.0.0.1:8889", timeout: float = 900,
                 provenance: ProvenanceLog | None = None, partition_url: str | None = None, check_version: bool = False):
        store = HindsightStore(gate, base_url, partition_url, timeout)
        super().__init__(gate, store, bank, provenance)
        # The store's requests go through `_call`, looked up at call time, so a test (or a host) can replace it.
        self._send = store.call
        store.call = lambda *a, **k: self._call(*a, **k)
        if check_version:
            self.check_version()

    # -- the names integrations, tools and tests already use (compatibility; prefer the Memory API) -----
    @property
    def bank(self) -> str:
        return self.core.shared

    @bank.setter
    def bank(self, value: str) -> None:
        self.core.shared = value

    @property
    def base_url(self) -> str:
        return self.store.base_url

    @property
    def partition_url(self) -> str | None:
        return self.store.partition_url

    @property
    def provenance(self) -> ProvenanceLog | None:
        return self.core.provenance

    def partitions(self) -> list[str]:
        return self.core.partitions()

    def _base_for(self, path: str) -> str:
        return self.store.base_for(path)

    def _call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
              location: str | None = None, role: str = "agent") -> dict:
        """One request to the server, with memgate's headers. Replace it to fake the server."""
        return self._send(method, path, body, agent=agent, location=location, role=role)

    def _ensure(self, bank: str) -> None:
        self.store.ensure(bank)

    def check_version(self) -> dict:
        """One gated request per server, so a worker on the wrong release fails at construction
        (VersionMismatch) rather than on its first write."""
        return self.store.check_version(self.core.shared)

    def recall(self, ctx, query: str, k: int = 20, budget: str = "mid") -> RecallBatch:
        """See `Memory.recall`; `budget` is Hindsight's recall budget (low, mid, high)."""
        return super().recall(ctx, query, k, budget=budget)


class AsyncHindsightMemory(AsyncMemory):
    """The same API for asyncio hosts. Needs httpx (`pip install 'memgate[async]'`). Use it as an async
    context manager, or call `aclose()` when done. There is no `check_version=` here (a constructor can't
    await): call `await mem.check_version()` once after constructing it."""

    def __init__(self, gate: Gate, bank: str, base_url: str = "http://127.0.0.1:8889", timeout: float = 900,
                 provenance: ProvenanceLog | None = None, partition_url: str | None = None):
        store = AsyncHindsightStore(gate, base_url, partition_url, timeout)
        super().__init__(gate, store, bank, provenance)
        self._send = store.call

        async def routed(*a, **k):
            return await self._call(*a, **k)
        store.call = routed

    @property
    def bank(self) -> str:
        return self.core.shared

    @bank.setter
    def bank(self, value: str) -> None:
        self.core.shared = value

    @property
    def base_url(self) -> str:
        return self.store.base_url

    @property
    def partition_url(self) -> str | None:
        return self.store.partition_url

    @property
    def provenance(self) -> ProvenanceLog | None:
        return self.core.provenance

    def partitions(self) -> list[str]:
        return self.core.partitions()

    def _base_for(self, path: str) -> str:
        return self.store.base_for(path)

    @property
    def _http(self):
        """The httpx client for the shared server (kept for tests that check it never uses a proxy)."""
        return self.store._client(self.store.base_url)

    async def _call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
                    location: str | None = None, role: str = "agent") -> dict:
        return await self._send(method, path, body, agent=agent, location=location, role=role)

    async def check_version(self) -> dict:
        """See `HindsightMemory.check_version`."""
        return await self.store.check_version(self.core.shared)

    async def recall(self, ctx, query: str, k: int = 20, budget: str = "mid") -> RecallBatch:
        """See `Memory.recall`."""
        return await super().recall(ctx, query, k, budget=budget)
