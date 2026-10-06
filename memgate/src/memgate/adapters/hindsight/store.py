"""Hindsight as a memgate store (memgate.store.Store): banks are partitions, tags are label sets,
document IDs are write IDs.

Hindsight offers every optional capability: the validator (memgate.adapters.hindsight.validator) is the
second lock inside the server; a retain with a known document_id replaces the earlier document; each
partition is a bank of its own; deleting a document takes the observations built on it; the admin
listing gives a label set's units; bank stats and per-bank consolidation settings exist.

A server address is `http://host:port` or `unix:/path/to/memgate.sock` (`memgate serve --socket`).
Requests carry the shared secret, so they never go through a proxy, and over a socket the store first
checks that the socket's directory is private and owned by this user. Partitions can live on a server
of their own (`partition_url`).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import socket
import stat
import urllib.error
import urllib.parse
import urllib.request

from memgate import __version__
from memgate.context import (HEADER_AGENT, HEADER_LOCATION, HEADER_ROLE, HEADER_SECRET, HEADER_VERSION, PARTITION_SEP,
                             Gate)
from memgate.store import Capabilities, Hit, Item, Listed
_BANK_IN_PATH = re.compile(r"^/v1/default/banks/([^/?]+)")

# Requests carry memgate's shared secret, so they must never go through a proxy (urllib otherwise
# honours HTTP_PROXY / HTTPS_PROXY from the environment, and a proxy would see the header).
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Hindsight's per-bank settings that keep a partition from consolidating (no observations, no post-write
# consolidation), set with PATCH .../config {"updates": ...}.
NO_CONSOLIDATION = {"enable_observations": False, "enable_auto_consolidation": False}

CAPABILITIES = Capabilities(second_lock=True, idempotent_replace=True, partitions=True, delete=True,
                            list_by_label_set=True, stats=True, consolidation_control=True)


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


class VersionMismatch(HindsightError):
    """The server refused this client's release (status 426 from the validator): the client is newer than
    the server (upgrade the server first) or below the server's minimum (a stale worker)."""


def _hit(r: dict) -> Hit:
    tags = r.get("tags") or []
    when = r.get("occurred_start") or r.get("mentioned_at")
    return Hit(r["text"], tags[0] if tags else "", str(when)[:10] if when else None, r.get("document_id"),
               float((r.get("scores") or {}).get("final") or 0.0))


def _listed(u: dict) -> Listed:
    when = u.get("occurred_start") or u.get("mentioned_at")
    tags = u.get("tags") or []
    return Listed(write_id=u.get("document_id") or u["id"], label_set=tags[0] if tags else "", text=u.get("text", ""),
                  when=str(when)[:7] if when else None,
                  kind="derived" if u.get("fact_type") == "observation" else "memory",
                  sources=list(u.get("source_memory_ids") or []))


class _Routing:
    """Shared by the sync and async stores: addresses, headers, routing of partitions to servers. `_ensured`
    and `_consolidation` are per-process caches of idempotent requests; two threads may both send one."""

    def __init__(self, gate: Gate, base_url: str, partition_url: str | None, timeout: float):
        self.gate, self.base_url, self.timeout = gate, base_url.rstrip("/"), timeout
        self.partition_url = partition_url.rstrip("/") if partition_url else None
        self._ensured: set[str] = set()
        self._consolidation: dict[str, bool] = {}
        self.capabilities = CAPABILITIES

    def base_for(self, path: str) -> str:
        """The server a request goes to: partitions to `partition_url` when set, all else to `base_url`."""
        m = _BANK_IN_PATH.match(path)
        if self.partition_url and m and PARTITION_SEP in m.group(1):
            return self.partition_url
        return self.base_url

    def headers(self, agent: str | None, location: str | None, role: str) -> dict:
        h = {"Content-Type": "application/json", HEADER_SECRET: self.gate.secret, HEADER_ROLE: role,
             HEADER_VERSION: __version__}
        if agent:
            h[HEADER_AGENT] = agent
        if location:
            h[HEADER_LOCATION] = location
        return h

    @staticmethod
    def retain_body(item: Item) -> dict:
        return {"items": [{"content": item.text, "tags": [item.label_set], "context": item.about,
                           "document_id": item.write_id,
                           "timestamp": item.when.isoformat() if hasattr(item.when, "isoformat") else item.when}]}

    @staticmethod
    def recall_body(query: str, allowed: set[str], budget: str) -> dict:
        return {"query": query, "budget": budget, "tags": sorted(allowed) or ["ls_none"], "tags_match": "any_strict"}

    @staticmethod
    def unfinished(ops) -> int:
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        return sum(o.get("status") not in ("completed", "failed", "cancelled") for o in ops)

    @staticmethod
    def raise_for(status: int, raw: str) -> None:
        if status >= 400:
            if status == 426:
                raise VersionMismatch(status, raw)
            raise HindsightError(status, raw)


class HindsightStore(_Routing):
    """Synchronous (urllib, no dependencies)."""

    def call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
             location: str | None = None, role: str = "agent") -> dict:
        status, raw = send(self.base_for(path), method, path, json.dumps(body).encode() if body is not None else None,
                           self.headers(agent, location, role), self.timeout)
        self.raise_for(status, raw.decode(errors="replace"))
        return json.loads(raw) if raw else {}

    def _handshake_paths(self, shared: str) -> list[str]:
        """Requests the validator gates (bank stats, admin), one per server; a missing bank is a 404 after the
        version check, which is what we want to see."""
        paths = [f"/v1/default/banks/{shared}/stats"]
        if self.partition_url:
            paths.append(f"/v1/default/banks/{shared}{PARTITION_SEP}check/stats")   # routed to the partition server
        return paths

    def check_version(self, shared: str = "memgate") -> dict:
        """One gated request per server at construction, so a worker on the wrong release fails at boot
        (VersionMismatch), not on its first write. Returns {"client": ..., "servers": n}."""
        for path in self._handshake_paths(shared):
            try:
                self.call("GET", path, None, role="admin")
            except HindsightError as e:
                if isinstance(e, VersionMismatch) or e.status != 404:
                    raise
        return {"client": __version__, "servers": 1 + bool(self.partition_url)}

    def ensure(self, partition: str, *, consolidate: bool = True) -> None:
        if partition not in self._ensured:
            self.call("PUT", f"/v1/default/banks/{partition}", {"name": partition}, role="admin")   # idempotent
            self._ensured.add(partition)
        if not consolidate and self._consolidation.get(partition, True):
            self.call("PATCH", f"/v1/default/banks/{partition}/config", {"updates": NO_CONSOLIDATION}, role="admin")
            self._consolidation[partition] = False

    def put(self, item: Item, *, agent: str | None, location: str | None) -> None:
        self.call("POST", f"/v1/default/banks/{item.partition}/memories", self.retain_body(item), agent=agent, location=location)

    def search(self, partitions: list[str], query: str, allowed: set[str], k: int, *, agent: str | None,
               location: str | None, budget: str = "mid") -> list[Hit]:
        hits: list[Hit] = []
        for p in partitions:
            resp = self.call("POST", f"/v1/default/banks/{p}/memories/recall", self.recall_body(query, allowed, budget),
                             agent=agent, location=location)
            hits += [_hit(r) for r in resp.get("results", [])]
        return hits

    def pending(self, partitions: list[str]) -> int:
        total = 0
        for p in partitions:
            try:
                total += self.unfinished(self.call("GET", f"/v1/default/banks/{p}/operations", None, role="admin"))
            except HindsightError as e:
                if e.status != 404:          # 404: a partition nothing has been written to yet
                    raise
        return total

    def delete(self, partition: str, write_id: str) -> bool:
        try:
            self.call("DELETE", f"/v1/default/banks/{partition}/documents/{urllib.parse.quote(write_id, safe='')}", None, role="admin")
            return True
        except HindsightError as e:
            if e.status == 404:
                return False
            raise

    def _pages(self, path: str, size: int = 500) -> list[dict]:
        out, offset = [], 0
        while True:
            sep = "&" if "?" in path else "?"
            r = self.call("GET", f"{path}{sep}limit={size}&offset={offset}", None, role="admin")
            items = r.get("items", [])
            out += items
            offset += len(items)
            if not items or offset >= r.get("total", 0):
                return out

    def list(self, partition: str, label_set: str) -> list[Listed]:
        try:
            units = self._pages(f"/v1/default/banks/{partition}/memories/list?tags={urllib.parse.quote(label_set, safe='')}&tags_match=all_strict")
        except HindsightError as e:
            if e.status == 404:                        # a partition nothing has been written to yet
                return []
            raise
        by_unit = {u["id"]: u.get("document_id") or u["id"] for u in units}
        out = []
        for u in units:
            if (u.get("tags") or [None])[0] != label_set:
                continue                      # a store that ignored the filter: never show another set's items
            item = _listed(u)
            item.sources = [by_unit.get(s, s) for s in item.sources]
            out.append(item)
        return out

    def stats(self, partition: str, label_sets: list[str] | None = None) -> dict:
        try:
            st = self.call("GET", f"/v1/default/banks/{partition}/stats", None, role="admin")
            ops = self.call("GET", f"/v1/default/banks/{partition}/operations", None, role="admin")
        except HindsightError as e:
            if e.status == 404:
                return {"exists": False}
            raise
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        consolidations = [o for o in ops if o.get("task_type") == "consolidation"]
        out = {"exists": True, "stats": st, "pending": self.unfinished(ops),
               "last_consolidation": max((o.get("completed_at") or o.get("created_at") or "" for o in consolidations), default=None)}
        if label_sets:
            out["label_sets"] = {}
            for ls in label_sets:
                units = self._pages(f"/v1/default/banks/{partition}/memories/list?tags={urllib.parse.quote(ls, safe='')}&tags_match=all_strict")
                units = [u for u in units if (u.get("tags") or [None])[0] == ls]
                out["label_sets"][ls] = {
                    "memories": sum(u.get("fact_type") != "observation" for u in units),
                    "observations": sum(u.get("fact_type") == "observation" for u in units),
                    "documents": len({u.get("document_id") for u in units if u.get("document_id")}),
                    "last_write": max((str(u.get("mentioned_at") or u.get("occurred_start") or "") for u in units), default=None),
                }
        return out


class AsyncHindsightStore(_Routing):
    """The same store for asyncio hosts. Needs httpx (`pip install 'memgate[async]'`)."""

    def __init__(self, gate: Gate, base_url: str, partition_url: str | None, timeout: float):
        import httpx
        super().__init__(gate, base_url, partition_url, timeout)
        self._httpx = httpx
        self._clients: dict[str, object] = {}

    def _client(self, base: str):
        if base not in self._clients:
            sock = socket_path(base)
            transport = self._httpx.AsyncHTTPTransport(uds=sock) if sock else None
            self._clients[base] = self._httpx.AsyncClient(timeout=self.timeout, trust_env=False, transport=transport)
        return self._clients[base]

    async def aclose(self) -> None:
        for c in self._clients.values():
            await c.aclose()
        self._clients.clear()

    async def call(self, method: str, path: str, body: dict | None, *, agent: str | None = None,
                   location: str | None = None, role: str = "agent") -> dict:
        base = self.base_for(path)
        sock = socket_path(base)
        if sock:
            check_socket(sock)
        r = await self._client(base).request(method, f"{'http://memgate' if sock else base}{path}",
                                             headers=self.headers(agent, location, role),
                                             content=json.dumps(body).encode() if body is not None else None)
        self.raise_for(r.status_code, r.text)
        return r.json() if r.content else {}

    async def check_version(self, shared: str = "memgate") -> dict:
        for path in self._handshake_paths(shared):
            try:
                await self.call("GET", path, None, role="admin")
            except HindsightError as e:
                if isinstance(e, VersionMismatch) or e.status != 404:
                    raise
        return {"client": __version__, "servers": 1 + bool(self.partition_url)}

    async def ensure(self, partition: str, *, consolidate: bool = True) -> None:
        if partition not in self._ensured:
            await self.call("PUT", f"/v1/default/banks/{partition}", {"name": partition}, role="admin")
            self._ensured.add(partition)
        if not consolidate and self._consolidation.get(partition, True):
            await self.call("PATCH", f"/v1/default/banks/{partition}/config", {"updates": NO_CONSOLIDATION}, role="admin")
            self._consolidation[partition] = False

    async def put(self, item: Item, *, agent: str | None, location: str | None) -> None:
        await self.call("POST", f"/v1/default/banks/{item.partition}/memories", self.retain_body(item), agent=agent, location=location)

    async def search(self, partitions: list[str], query: str, allowed: set[str], k: int, *, agent: str | None,
                     location: str | None, budget: str = "mid") -> list[Hit]:
        hits: list[Hit] = []
        for p in partitions:
            resp = await self.call("POST", f"/v1/default/banks/{p}/memories/recall", self.recall_body(query, allowed, budget),
                                   agent=agent, location=location)
            hits += [_hit(r) for r in resp.get("results", [])]
        return hits

    async def pending(self, partitions: list[str]) -> int:
        total = 0
        for p in partitions:
            try:
                total += self.unfinished(await self.call("GET", f"/v1/default/banks/{p}/operations", None, role="admin"))
            except HindsightError as e:
                if e.status != 404:
                    raise
        return total

    async def delete(self, partition: str, write_id: str) -> bool:
        try:
            await self.call("DELETE", f"/v1/default/banks/{partition}/documents/{urllib.parse.quote(write_id, safe='')}", None, role="admin")
            return True
        except HindsightError as e:
            if e.status == 404:
                return False
            raise

    async def _pages(self, path: str, size: int = 500) -> list[dict]:
        out, offset = [], 0
        while True:
            sep = "&" if "?" in path else "?"
            r = await self.call("GET", f"{path}{sep}limit={size}&offset={offset}", None, role="admin")
            items = r.get("items", [])
            out += items
            offset += len(items)
            if not items or offset >= r.get("total", 0):
                return out

    async def list(self, partition: str, label_set: str) -> list[Listed]:
        try:
            units = await self._pages(f"/v1/default/banks/{partition}/memories/list?tags={urllib.parse.quote(label_set, safe='')}&tags_match=all_strict")
        except HindsightError as e:
            if e.status == 404:
                return []
            raise
        by_unit = {u["id"]: u.get("document_id") or u["id"] for u in units}
        out = []
        for u in units:
            if (u.get("tags") or [None])[0] != label_set:
                continue
            item = _listed(u)
            item.sources = [by_unit.get(s, s) for s in item.sources]
            out.append(item)
        return out

    async def stats(self, partition: str, label_sets: list[str] | None = None) -> dict:
        try:
            st = await self.call("GET", f"/v1/default/banks/{partition}/stats", None, role="admin")
            ops = await self.call("GET", f"/v1/default/banks/{partition}/operations", None, role="admin")
        except HindsightError as e:
            if e.status == 404:
                return {"exists": False}
            raise
        ops = ops.get("operations", ops if isinstance(ops, list) else [])
        consolidations = [o for o in ops if o.get("task_type") == "consolidation"]
        out = {"exists": True, "stats": st, "pending": self.unfinished(ops),
               "last_consolidation": max((o.get("completed_at") or o.get("created_at") or "" for o in consolidations), default=None)}
        if label_sets:
            out["label_sets"] = {}
            for ls in label_sets:
                units = await self._pages(f"/v1/default/banks/{partition}/memories/list?tags={urllib.parse.quote(ls, safe='')}&tags_match=all_strict")
                units = [u for u in units if (u.get("tags") or [None])[0] == ls]
                out["label_sets"][ls] = {
                    "memories": sum(u.get("fact_type") != "observation" for u in units),
                    "observations": sum(u.get("fact_type") == "observation" for u in units),
                    "documents": len({u.get("document_id") for u in units if u.get("document_id")}),
                    "last_write": max((str(u.get("mentioned_at") or u.get("occurred_start") or "") for u in units), default=None),
                }
        return out
