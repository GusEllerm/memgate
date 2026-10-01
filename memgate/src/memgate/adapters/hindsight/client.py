"""memgate's Hindsight clients: the only way agents' memory reaches Hindsight.

They label every write from the context, register the label set, and tag the item with its ID.
On recall they compute the allowed label sets themselves (first lock) and pass them as tags; the
validator inside Hindsight recomputes and overwrites them (second lock). One shared bank holds the
world's ordinary locations and personal memory; each high-assurance location has its own bank (its
partition, `partition_bank`). A write goes to the partition of the high-assurance location it is
labelled with, if any; a recall in a high-assurance location searches its partition and the shared
bank (where personal memory lives) and merges them by score; a recall anywhere else never touches a
partition. Partitions can live on a server of their own (`partition_url`), for isolation.

`HindsightMemory` is synchronous (urllib, no dependencies); `AsyncHindsightMemory` is the same API
for asyncio hosts (needs httpx: `pip install 'memgate[async]'`). Both share `_Core`, which holds
every permission decision and does no I/O.

A server address is `http://host:port` or `unix:/path/to/memgate.sock` (`memgate serve --socket`).
Requests carry the shared secret, so they never go through a proxy, and over a socket the client
first checks that the socket's directory is private and owned by this user: only this user could
have created it, so nothing else can be listening there to collect the secret.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from memgate.context import (HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, PARTITION_SEP, Context,
                             Gate, partition_bank)
from memgate.derivation import personal_labels, personal_note_labels
from memgate.labels import LabelSet
from memgate.provenance import ProvenanceLog, new_id

_BANK_IN_PATH = re.compile(r"^/v1/default/banks/([^/?]+)")

# Requests carry memgate's shared secret, so they must never go through a proxy (urllib otherwise
# honours HTTP_PROXY / HTTPS_PROXY from the environment, and a proxy would see the header).
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def socket_path(base: str) -> str | None:
    """The socket path of a `unix:` server address, or None for an http address."""
    if not base.startswith("unix:"):
        return None
    path = base[len("unix:"):]
    return "/" + path.lstrip("/") if path.startswith("//") else path


def check_socket(path: str) -> None:
    """Refuse a socket that someone other than this user could have created (PermissionError)."""
    directory = os.path.dirname(os.path.abspath(path))
    d = os.stat(directory)
    if d.st_uid != os.getuid() or d.st_mode & 0o077:
        raise PermissionError(f"refusing {path}: its directory must be private (0700) and owned by this user, "
                              "so that nothing else can be listening there")
    s = os.stat(path)
    if not stat.S_ISSOCK(s.st_mode) or s.st_uid != os.getuid():
        raise PermissionError(f"refusing {path}: not a socket owned by this user")


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float):
        super().__init__("memgate", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._path)


def send(base: str, method: str, path: str, body: bytes | None, headers: dict, timeout: float) -> tuple[int, bytes]:
    """One HTTP request to a memgate server (http or unix address), never through a proxy."""
    sock = socket_path(base)
    if sock:
        check_socket(sock)
        conn = _UnixHTTPConnection(sock, timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            return r.status, r.read()
        finally:
            conn.close()
    req = urllib.request.Request(f"{base}{path}", method=method, headers=headers, data=body)
    try:
        with _DIRECT.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class HindsightError(RuntimeError):
    def __init__(self, status: int, body: str):
        self.status, self.body = status, body
        super().__init__(f"Hindsight {status}: {body[:300]}")


@dataclass
class Recalled:
    text: str
    label_set: str
    when: str | None
    write_id: str | None = None   # the memgate write this memory came from (Hindsight's document_id)


class RecallBatch(list):
    """The memories a recall returned, plus the provenance ID of the recall itself."""
    recall_id: str | None = None


class _Core:
    """Everything but the transport: labels, permission checks, routing, provenance."""

    def __init__(self, gate: Gate, bank: str, base_url: str = "http://127.0.0.1:8889", timeout: float = 900,
                 provenance: ProvenanceLog | None = None, partition_url: str | None = None):
        self.gate, self.bank, self.base_url, self.timeout = gate, bank, base_url.rstrip("/"), timeout
        self.partition_url = partition_url.rstrip("/") if partition_url else None
        self.provenance = provenance
        self._created: set[str] = set()

    # -- routing ------------------------------------------------------------------------------------
    def _base_for(self, path: str) -> str:
        """The server a request goes to: partitions to `partition_url` when set, all else to `base_url`."""
        m = _BANK_IN_PATH.match(path)
        if self.partition_url and m and PARTITION_SEP in m.group(1):
            return self.partition_url
        return self.base_url

    def _headers(self, agent: str | None, location: str | None, role: str) -> dict:
        h = {"Content-Type": "application/json", HEADER_SECRET: self.gate.secret, HEADER_ROLE: role}
        if agent:
            h[HEADER_AGENT] = agent
        if location:
            h[HEADER_LOCATION] = location
        return h

    def partitions(self) -> list[str]:
        """The shared bank and one partition per high-assurance location in the world."""
        w = self.gate.world
        return [self.bank] + [partition_bank(self.bank, l) for l in sorted(w.locations) if w.high_assurance(l)]

    def bank_for(self, labels: LabelSet) -> str:
        """Where a memory with these labels is stored."""
        ha = sorted(l for l in labels.locs if self.gate.world.high_assurance(l))
        return partition_bank(self.bank, ha[0]) if ha else self.bank

    # -- decisions (no I/O) ------------------------------------------------------------------------
    def _plan_write(self, agent: str, location: str, labels: LabelSet, text: str, when: datetime | None,
                    about: str | None) -> tuple[str, dict, str, str]:
        """Check and label a write: (bank, request body, label-set ID, write ID). Raises PermissionError."""
        if not self.gate.policy.may_write(agent, location, labels):
            raise PermissionError(f"{agent} may not write {labels} at {location}")
        ls_id = self.gate.registry.register(labels)
        write_id = new_id("w")
        item = {"content": text, "tags": [ls_id], "context": about, "document_id": write_id,
                "timestamp": when.isoformat() if when else None}
        return self.bank_for(labels), {"items": [item]}, ls_id, write_id

    def _after_write(self, agent: str, location: str, ls_id: str, write_id: str, kind: str, text: str,
                     turns=(), derived_from=()) -> None:
        if self.provenance:
            self.provenance.record_write(write_id, agent, location, ls_id, kind, text, turns=turns, derived_from=derived_from)
            self.provenance.audit(location, "write", write_id=write_id, agent=agent, label_set=ls_id, kind=kind)

    def _resolve_source(self, ctx: Context, source) -> tuple[LabelSet, list[str]]:
        """A carry-out's source as a label set, plus the writes it came from when known."""
        if source is None:
            return ctx.conversation(), []
        if isinstance(source, Recalled):
            return self.gate.registry.get(source.label_set), [source.write_id] if source.write_id else []
        if isinstance(source, str):
            return self.gate.registry.get(source), []
        return source, []

    def _plan_carry_out(self, ctx: Context, memory_type: str, source, source_writes) -> list[str]:
        """Check a carry-out; returns the writes it derives from. Raises PermissionError if refused."""
        labels, writes = self._resolve_source(ctx, source)
        allowed = self.gate.policy.may_carry_out(ctx.agent, ctx.location, labels, memory_type)
        if self.provenance:
            self.provenance.audit(ctx.location, "carry_out", agent=ctx.agent, source=labels.id,
                                  memory_type=memory_type, allowed=allowed)
        if not allowed:
            raise PermissionError(f"{memory_type} may not be carried out of {labels}")
        return list(source_writes) or writes

    def _plan_recall(self, ctx: Context, query: str, budget: str) -> tuple[set[str], list[str], dict]:
        allowed_set = self.gate.policy.allowed_ids(ctx.agent, ctx.location)
        body = {"query": query, "budget": budget, "tags": sorted(allowed_set) or ["ls_none"], "tags_match": "any_strict"}
        banks = [self.bank]
        if self.gate.world.high_assurance(ctx.location):
            banks.append(partition_bank(self.bank, ctx.location))      # at most two partitions per recall
        return allowed_set, banks, body

    def _finish_recall(self, ctx: Context, query: str, allowed_set: set[str], results: list[dict], merged: bool,
                       k: int) -> RecallBatch:
        if merged:
            results.sort(key=lambda r: -((r.get("scores") or {}).get("final") or 0.0))
        out = RecallBatch()
        for r in results[:k]:
            tags = r.get("tags") or []
            when = r.get("occurred_start") or r.get("mentioned_at")
            out.append(Recalled(r["text"], tags[0] if tags else "", str(when)[:10] if when else None, r.get("document_id")))
        if self.provenance:
            returned = [(m.write_id, m.label_set) for m in out if m.write_id]
            out.recall_id = self.provenance.record_recall(ctx.agent, ctx.location, query, allowed_set, returned)
            self.provenance.audit(ctx.location, "recall", agent=ctx.agent, allowed=len(allowed_set), returned=len(out))
        return out

    @staticmethod
    def _unfinished(ops) -> int:
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        return sum(o.get("status") not in ("completed", "failed", "cancelled") for o in ops)


class HindsightMemory(_Core):
    """Synchronous client. Every method takes a `Context`, built by the host from verified facts."""

    def _call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
              location: str | None = None, role: str = "agent") -> dict:
        status, raw = send(self._base_for(path), method, path, json.dumps(body).encode() if body is not None else None,
                           self._headers(agent, location, role), self.timeout)
        if status >= 400:
            raise HindsightError(status, raw.decode(errors="replace"))
        return json.loads(raw) if raw else {}

    def create_bank(self) -> None:
        self._ensure(self.bank)

    def _ensure(self, bank: str) -> None:
        if bank not in self._created:
            self._call("PUT", f"/v1/default/banks/{bank}", {"name": bank}, role="admin")   # idempotent
            self._created.add(bank)

    def _retain(self, agent: str, location: str, labels: LabelSet, text: str, when: datetime | None,
                about: str | None, kind: str, turns=(), derived_from=()) -> str:
        bank, body, ls_id, write_id = self._plan_write(agent, location, labels, text, when, about)
        self._ensure(bank)
        self._call("POST", f"/v1/default/banks/{bank}/memories", body, agent=agent, location=location)
        self._after_write(agent, location, ls_id, write_id, kind, text, turns, derived_from)
        return write_id

    def remember(self, ctx: Context, text: str, *, when: datetime | None = None, about: str | None = None,
                 turns: list[str] = ()) -> str:
        """Store something said or seen in `ctx`'s conversation (its location, among its participants).
        `about` is a short description for the memory system; `turns` are the provenance IDs of the
        turns (see `say`) it was formed from. Returns the write ID."""
        return self._retain(ctx.agent, ctx.location, ctx.conversation(), text, when, about, "conversation", turns=turns)

    def keep_note(self, ctx: Context, text: str, *, when: datetime | None = None) -> str:
        """A personal note that stays where it was written (e.g. inside a high-assurance location)."""
        return self._retain(ctx.agent, ctx.location, personal_note_labels(ctx.agent, ctx.location), text, when,
                            "personal note", "note")

    def carry_out(self, ctx: Context, text: str, memory_type: str, *, source: LabelSet | Recalled | str | None = None,
                  when: datetime | None = None, source_writes: list[str] = ()) -> str:
        """Copy something into the agent's personal memory, if every environment it came from allows.

        `source` is what the content was formed under: a recalled memory (its label set and write),
        a label set or its ID, or by default `ctx`'s conversation. It must be readable in `ctx`
        (Cedar checks). `memory_type` is the agent's own classification (fact, opinion, skill,
        episode), audited. Raises PermissionError if refused."""
        writes = self._plan_carry_out(ctx, memory_type, source, source_writes)
        return self._retain(ctx.agent, ctx.location, personal_labels(ctx.agent), text, when,
                            f"carried out ({memory_type})", "carry_out", derived_from=writes)

    def say(self, ctx: Context, text: str, recalls: list[str] = ()) -> str | None:
        """Record what `ctx.agent` said, to `ctx.participants`, and which recalls (their `recall_id`s)
        it drew on; returns the turn's provenance ID (None without a provenance log)."""
        if not self.provenance:
            return None
        return self.provenance.record_turn(ctx.agent, ctx.location, list(ctx.participants), text, list(recalls))

    def recall(self, ctx: Context, query: str, k: int = 20, budget: str = "mid") -> RecallBatch:
        """The memories `ctx.agent` may recall at `ctx.location` that best match `query`, best first."""
        allowed_set, banks, body = self._plan_recall(ctx, query, budget)
        results = []
        for bank in banks:
            self._ensure(bank)
            results += self._call("POST", f"/v1/default/banks/{bank}/memories/recall", body,
                                  agent=ctx.agent, location=ctx.location).get("results", [])
        return self._finish_recall(ctx, query, allowed_set, results, len(banks) > 1, k)

    def pending_operations(self) -> int:
        """Background operations not yet finished, across the shared bank and every partition in use."""
        total = 0
        for bank in self.partitions():
            try:
                total += self._unfinished(self._call("GET", f"/v1/default/banks/{bank}/operations", None, role="admin"))
            except HindsightError as e:
                if e.status != 404:          # 404: a partition nothing has been written to yet
                    raise
        return total


class AsyncHindsightMemory(_Core):
    """The same API as `HindsightMemory`, for asyncio hosts. Needs httpx (`pip install 'memgate[async]'`).
    Use it as an async context manager, or call `aclose()` when done."""

    def __init__(self, *args, **kwargs):
        import httpx
        super().__init__(*args, **kwargs)
        self._httpx = httpx
        self._clients: dict[str, object] = {}      # one per server address

    def _client(self, base: str):
        if base not in self._clients:
            sock = socket_path(base)
            transport = self._httpx.AsyncHTTPTransport(uds=sock) if sock else None
            # trust_env=False: never via a proxy (see _DIRECT).
            self._clients[base] = self._httpx.AsyncClient(timeout=self.timeout, trust_env=False, transport=transport)
        return self._clients[base]

    @property
    def _http(self):
        return self._client(self.base_url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def aclose(self) -> None:
        for c in self._clients.values():
            await c.aclose()
        self._clients.clear()

    async def _call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
                    location: str | None = None, role: str = "agent") -> dict:
        base = self._base_for(path)
        sock = socket_path(base)
        if sock:
            check_socket(sock)
        r = await self._client(base).request(method, f"{'http://memgate' if sock else base}{path}",
                                             headers=self._headers(agent, location, role),
                                             content=json.dumps(body).encode() if body is not None else None)
        if r.status_code >= 400:
            raise HindsightError(r.status_code, r.text)
        return r.json() if r.content else {}

    async def create_bank(self) -> None:
        await self._ensure(self.bank)

    async def _ensure(self, bank: str) -> None:
        if bank not in self._created:
            await self._call("PUT", f"/v1/default/banks/{bank}", {"name": bank}, role="admin")
            self._created.add(bank)

    async def _retain(self, agent: str, location: str, labels: LabelSet, text: str, when: datetime | None,
                      about: str | None, kind: str, turns=(), derived_from=()) -> str:
        bank, body, ls_id, write_id = self._plan_write(agent, location, labels, text, when, about)
        await self._ensure(bank)
        await self._call("POST", f"/v1/default/banks/{bank}/memories", body, agent=agent, location=location)
        self._after_write(agent, location, ls_id, write_id, kind, text, turns, derived_from)
        return write_id

    async def remember(self, ctx: Context, text: str, *, when: datetime | None = None, about: str | None = None,
                       turns: list[str] = ()) -> str:
        """See `HindsightMemory.remember`."""
        return await self._retain(ctx.agent, ctx.location, ctx.conversation(), text, when, about, "conversation", turns=turns)

    async def keep_note(self, ctx: Context, text: str, *, when: datetime | None = None) -> str:
        """See `HindsightMemory.keep_note`."""
        return await self._retain(ctx.agent, ctx.location, personal_note_labels(ctx.agent, ctx.location), text, when,
                                  "personal note", "note")

    async def carry_out(self, ctx: Context, text: str, memory_type: str, *,
                        source: LabelSet | Recalled | str | None = None, when: datetime | None = None,
                        source_writes: list[str] = ()) -> str:
        """See `HindsightMemory.carry_out`."""
        writes = self._plan_carry_out(ctx, memory_type, source, source_writes)
        return await self._retain(ctx.agent, ctx.location, personal_labels(ctx.agent), text, when,
                                  f"carried out ({memory_type})", "carry_out", derived_from=writes)

    async def say(self, ctx: Context, text: str, recalls: list[str] = ()) -> str | None:
        """See `HindsightMemory.say`."""
        if not self.provenance:
            return None
        return self.provenance.record_turn(ctx.agent, ctx.location, list(ctx.participants), text, list(recalls))

    async def recall(self, ctx: Context, query: str, k: int = 20, budget: str = "mid") -> RecallBatch:
        """See `HindsightMemory.recall`."""
        allowed_set, banks, body = self._plan_recall(ctx, query, budget)
        results = []
        for bank in banks:
            await self._ensure(bank)
            resp = await self._call("POST", f"/v1/default/banks/{bank}/memories/recall", body,
                                    agent=ctx.agent, location=ctx.location)
            results += resp.get("results", [])
        return self._finish_recall(ctx, query, allowed_set, results, len(banks) > 1, k)

    async def pending_operations(self) -> int:
        """See `HindsightMemory.pending_operations`."""
        total = 0
        for bank in self.partitions():
            try:
                total += self._unfinished(await self._call("GET", f"/v1/default/banks/{bank}/operations", None, role="admin"))
            except HindsightError as e:
                if e.status != 404:
                    raise
        return total
