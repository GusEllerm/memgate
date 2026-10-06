"""memgate's decisions, and the store-agnostic memory API built on them.

`Core` holds every permission decision and does no I/O: it labels writes, mints write IDs, chooses
partitions, checks carry-outs, computes the label sets a recall may read, and records provenance. It
knows nothing about any memory system. `Memory` and `AsyncMemory` put a `Store` (memgate.store) behind
it: the same decisions, whichever store keeps the memories. Adapters (memgate.adapters.*) supply the
stores; `HindsightMemory` and `AsyncHindsightMemory` are `Memory` and `AsyncMemory` with the Hindsight
store, kept as the names hosts already use.

Partitions: one shared partition holds every ordinary location's conversations and most personal
memory; each high-assurance location has a partition of its own (`partition_key`), so its memories
never share ranking statistics, caches or consolidation with anything outside it; and a class of
personal memory the world keeps out of consolidation (`World.consolidates` False) has one too
(`class_bank`), where the store is told not to consolidate. A write goes to the partition of the
high-assurance location it is labelled with, else of its non-consolidating class, else the shared one.
A recall searches the shared partition, every class partition (personal memory is readable everywhere
its owner is) and, inside a high-assurance location, that location's partition.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime

from memgate.context import Context, Gate, class_bank, partition_bank
from memgate.derivation import personal_labels, personal_note_labels
from memgate.labels import CLASSES, LabelSet, class_rank, strictest
from memgate.provenance import ProvenanceLog, write_id_for, write_id_label_set
from memgate.store import Capabilities, Hit, Item, Listed, Store

log = logging.getLogger("memgate")

partition_key = partition_bank


@dataclass
class Recalled:
    text: str
    label_set: str
    when: str | None
    write_id: str | None = None   # the memgate write this memory came from


class RecallBatch(list):
    """The memories a recall returned, plus the provenance ID of the recall itself."""
    recall_id: str | None = None


def _event(event: str, **fields) -> None:
    """One structured log line (JSON, no memory text or query text ever)."""
    if log.isEnabledFor(logging.INFO):
        log.info(json.dumps({"event": event, "ts": round(time.time(), 3), **fields}, default=str))


class Core:
    """Everything but the store: labels, permission checks, routing, provenance. No I/O."""

    def __init__(self, gate: Gate, shared: str, provenance: ProvenanceLog | None = None):
        self.gate, self.shared, self.provenance = gate, shared, provenance

    # -- routing --------------------------------------------------------------------------------
    def class_partitions(self) -> list[str]:
        """One partition per class of personal memory the world keeps out of consolidation."""
        w = self.gate.world
        return [class_bank(self.shared, c) for c in CLASSES if not w.consolidates(c)]

    def partitions(self) -> list[str]:
        """The shared partition, the class partitions, and one per high-assurance location in the world."""
        w = self.gate.world
        return [self.shared] + self.class_partitions() + \
            [partition_key(self.shared, l) for l in sorted(w.locations) if w.high_assurance(l)]

    def partition_for(self, labels: LabelSet) -> str:
        """Where a memory with these labels is kept: its high-assurance location's partition, else its
        non-consolidating class's, else the shared one."""
        ha = sorted(l for l in labels.locs if self.gate.world.high_assurance(l))
        if ha:
            return partition_key(self.shared, ha[0])
        cls = strictest(labels.classes)
        if cls and not self.gate.world.consolidates(cls):
            return class_bank(self.shared, cls)
        return self.shared

    def partitions_for_recall(self, ctx: Context) -> list[str]:
        """The shared and class partitions, plus the location's own inside a high-assurance location."""
        parts = [self.shared] + self.class_partitions()
        if self.gate.world.high_assurance(ctx.location):
            parts.append(partition_key(self.shared, ctx.location))
        return parts

    # -- writes ---------------------------------------------------------------------------------
    def plan_write(self, agent: str, location: str, labels: LabelSet, text: str, when: datetime | None,
                   about: str | None, key: str | None = None) -> Item:
        """Check and label a write. Raises PermissionError. With a `key`, the write ID is derived from it
        (see `write_id_for`), so the same key under the same label set re-sent replaces the earlier write
        in a store with idempotent replace."""
        if not self.gate.policy.may_write(agent, location, labels):
            _event("refused", op="write", agent=agent, location=location, label_set=labels.id, why="policy")
            raise PermissionError(f"{agent} may not write {labels} at {location}")
        ls_id = self.gate.registry.register(labels)
        return Item(text=text, label_set=ls_id, write_id=write_id_for(ls_id, key), partition=self.partition_for(labels),
                    when=when, about=about, consolidate=self.gate.world.consolidates(strictest(labels.classes)))

    def record_write(self, agent: str, location: str, item: Item, kind: str, turns=(), derived_from=()) -> None:
        _event("write", kind=kind, agent=agent, location=location, label_set=item.label_set, write_id=item.write_id,
               partition=item.partition, chars=len(item.text))
        if self.provenance:
            self.provenance.record_write(item.write_id, agent, location, item.label_set, kind, item.text,
                                         turns=turns, derived_from=derived_from)
            self.provenance.audit(location, "write", write_id=item.write_id, agent=agent, label_set=item.label_set, kind=kind)

    # -- carry-out ------------------------------------------------------------------------------
    def resolve_source(self, ctx: Context, source) -> tuple[LabelSet, list[str]]:
        """A carry-out's source as a label set, plus the writes it came from when known."""
        if source is None:
            return ctx.conversation(), []
        if isinstance(source, Recalled):
            return self.gate.registry.get(source.label_set), [source.write_id] if source.write_id else []
        if isinstance(source, str):
            return self.gate.registry.get(source), []
        return source, []

    def plan_carry_out(self, ctx: Context, memory_type: str, source, source_writes, cls: str | None = None) -> list[str]:
        """Check a carry-out into the personal set of class `cls`; returns the writes it derives from.
        Raises PermissionError if refused.

        Cedar decides whether the content may leave (`Policy.may_carry_out`). Two class rules follow, both
        here on the client side, since a store never sees a carry-out, only the personal write it produces:
        content from a classed source never goes to a less strict class, and the `min_class` of the
        environment of ctx.location (and of any source location) must be met. Neither chooses a class."""
        class_rank(cls)                                     # an unknown class is a ValueError, not a refusal
        labels, writes = self.resolve_source(ctx, source)
        allowed, why = self.gate.policy.may_carry_out(ctx.agent, ctx.location, labels, memory_type), None
        if not allowed:
            why = f"{memory_type} may not be carried out of {labels}"
        elif class_rank(strictest(labels.classes)) > class_rank(cls):
            allowed, why = False, f"content of class {strictest(labels.classes)!r} may not go to {cls or 'unclassed'} personal memory"
        else:
            floor = self.gate.world.min_class(labels.locs | {ctx.location})
            if class_rank(floor) > class_rank(cls):
                allowed, why = False, f"carry-outs from {ctx.location} need class {floor!r} or stricter, not {cls or 'none'}"
        if self.provenance:
            self.provenance.audit(ctx.location, "carry_out", agent=ctx.agent, source=labels.id,
                                  memory_type=memory_type, cls=cls, allowed=allowed, **({"why": why} if why else {}))
        if not allowed:
            _event("refused", op="carry_out", agent=ctx.agent, location=ctx.location, source=labels.id,
                   memory_type=memory_type, cls=cls, why=why)
            raise PermissionError(why)
        return list(source_writes) or writes

    # -- recall ---------------------------------------------------------------------------------
    def plan_recall(self, ctx: Context) -> tuple[set[str], list[str]]:
        """The label sets `ctx` may read, and the partitions a recall there searches."""
        return self.gate.policy.allowed_ids(ctx.agent, ctx.location), self.partitions_for_recall(ctx)

    def finish_recall(self, ctx: Context, query: str, allowed: set[str], hits: list[Hit], k: int) -> RecallBatch:
        """Keep only what `allowed` permits (the client-side lock, whatever the store did; a hit with no label
        set is never returned), best first. Stores score higher-is-better; with every score 0 the stable sort
        keeps the store's own order, and a single store's order is already by score."""
        permitted = [h for h in hits if h.label_set in allowed]
        kept = sorted(permitted, key=lambda h: -h.score)[:k]
        out = RecallBatch(Recalled(h.text, h.label_set, h.when, h.write_id) for h in kept)
        dropped = len(hits) - len(permitted)
        _event("recall", agent=ctx.agent, location=ctx.location, allowed=len(allowed), returned=len(out),
               dropped_by_client=dropped, k=k)
        if self.provenance:
            returned = [(m.write_id, m.label_set) for m in out if m.write_id]
            out.recall_id = self.provenance.record_recall(ctx.agent, ctx.location, query, allowed, returned)
            self.provenance.audit(ctx.location, "recall", agent=ctx.agent, allowed=len(allowed), returned=len(out))
        return out

    def say(self, ctx: Context, text: str, recalls: list[str] = ()) -> str | None:
        if not self.provenance:
            return None
        return self.provenance.record_turn(ctx.agent, ctx.location, list(ctx.participants), text, list(recalls))

    # -- the owner's side: forget and list ------------------------------------------------------
    def owned_by(self, agent: str, write_id: str) -> str:
        """The label set a write ID was minted under, if it is one of `agent`'s personal sets (plain or any
        class); PermissionError otherwise. A host-trusted check: the host has verified the owner."""
        mine = {personal_labels(agent).id} | {personal_labels(agent, c).id for c in CLASSES}
        ls = write_id_label_set(write_id)
        if ls not in mine or not re.fullmatch(rf"w_{ls}_[0-9a-f]{{16}}", write_id):
            _event("refused", op="forget", agent=agent, write_id=write_id, why="not this agent's personal memory")
            raise PermissionError(f"{write_id} is not in {agent}'s personal memory")
        return ls

    def personal_sets(self, agent: str) -> list[tuple[str, str]]:
        """An agent's personal sets that exist in the registry, as (label-set ID, partition): plain first,
        then by class."""
        known = self.gate.registry.all()
        sets = [personal_labels(agent)] + [personal_labels(agent, c) for c in CLASSES]
        return [(ls.id, self.partition_for(ls)) for ls in sets if ls.id in known]

    def partition_of_write(self, write_id: str) -> str:
        """The partition a write ID's label set lives in (its label set is in the ID)."""
        ls = write_id_label_set(write_id)
        return self.partition_for(self.gate.registry.get(ls)) if ls in self.gate.registry.all() else self.shared


class Memory:
    """memgate over any synchronous `Store`. Every method takes a `Context` built by the host from
    verified facts. See INTEGRATION.md for the contract."""

    def __init__(self, gate: Gate, store: Store, shared: str, provenance: ProvenanceLog | None = None):
        self.core, self.store = Core(gate, shared, provenance), store
        self.gate = gate

    @property
    def capabilities(self) -> Capabilities:
        return self.store.capabilities

    def create_bank(self) -> None:
        """Make the shared partition exist (kept under its old name for hosts that call it)."""
        self.store.ensure(self.core.shared)

    def _keep(self, agent: str, location: str, labels: LabelSet, text: str, when, about, kind: str,
              turns=(), derived_from=(), key: str | None = None) -> str:
        item = self.core.plan_write(agent, location, labels, text, when, about, key)
        self.store.ensure(item.partition, consolidate=item.consolidate)
        self.store.put(item, agent=agent, location=location)
        self.core.record_write(agent, location, item, kind, turns, derived_from)
        return item.write_id

    def remember(self, ctx: Context, text: str, *, when: datetime | None = None, about: str | None = None,
                 turns: list[str] = (), key: str | None = None) -> str:
        """Store something said or seen in `ctx`'s conversation (its location, among its participants).
        `about` is a short description for the store's extraction; `turns` are the provenance IDs of the
        turns (see `say`) it was formed from. `key` makes the write idempotent in a store with idempotent
        replace: the same key from the same conversation re-sent replaces the earlier write. Returns the
        write ID."""
        return self._keep(ctx.agent, ctx.location, ctx.conversation(), text, when, about, "conversation", turns=turns, key=key)

    def keep_note(self, ctx: Context, text: str, *, when: datetime | None = None, key: str | None = None) -> str:
        """A personal note that stays where it was written (e.g. inside a high-assurance location)."""
        return self._keep(ctx.agent, ctx.location, personal_note_labels(ctx.agent, ctx.location), text, when,
                          "personal note", "note", key=key)

    def carry_out(self, ctx: Context, text: str, memory_type: str, *, source: LabelSet | Recalled | str | None = None,
                  when: datetime | None = None, source_writes: list[str] = (), key: str | None = None,
                  cls: str | None = None) -> str:
        """Copy something into the agent's personal memory, if every environment it came from allows.

        `source` is what the content was formed under: a recalled memory (its label set and write), a
        label set or its ID, or by default `ctx`'s conversation. It must be readable in `ctx` (Cedar
        checks). `memory_type` is the agent's own classification (fact, opinion, skill, episode),
        audited. `cls` files it in the agent's personal set of that class, kept apart from its other
        personal memory; content from a classed source keeps at least that class, and an environment's
        `min_class` must be met. `key` as in `remember`; a key must be unique across everything the agent
        carries out. Raises PermissionError if refused."""
        writes = self.core.plan_carry_out(ctx, memory_type, source, source_writes, cls)
        return self._keep(ctx.agent, ctx.location, personal_labels(ctx.agent, cls), text, when,
                          f"carried out ({memory_type})", "carry_out", derived_from=writes, key=key)

    def say(self, ctx: Context, text: str, recalls: list[str] = ()) -> str | None:
        """Record what `ctx.agent` said, to `ctx.participants`, and which recalls (their `recall_id`s) it
        drew on; returns the turn's provenance ID (None without a provenance log)."""
        return self.core.say(ctx, text, recalls)

    def recall(self, ctx: Context, query: str, k: int = 20, **store_options) -> RecallBatch:
        """The memories `ctx.agent` may recall at `ctx.location` that best match `query`, best first.
        `store_options` go to the store (Hindsight: `budget`)."""
        allowed, partitions = self.core.plan_recall(ctx)
        for p in partitions:
            self.store.ensure(p)
        hits = self.store.search(partitions, query, allowed, k, agent=ctx.agent, location=ctx.location, **store_options)
        return self.core.finish_recall(ctx, query, allowed, hits, k)

    def pending_operations(self) -> int:
        """Background operations not yet finished, across the shared partition and every partition in use."""
        return self.store.pending(self.core.partitions())

    # -- host-trusted owner operations (the host has verified the owner; the store is asked as admin) ----
    def forget(self, agent: str, write_id: str) -> bool:
        """Delete one item of `agent`'s personal memory (plain or classed) by write ID, with whatever the
        store derived from it. Needs capability `delete`. The host must also stop re-sending the item
        (a tombstone on its own record), or a replayed keyed write brings it back. Returns whether it
        existed."""
        if not self.store.capabilities.delete:
            raise NotImplementedError("this store cannot delete")
        self.core.owned_by(agent, write_id)
        existed = self.store.delete(self.core.partition_of_write(write_id), write_id)
        _event("forget", agent=agent, write_id=write_id, existed=existed)
        if self.core.provenance:
            self.core.provenance.audit(None, "forget", agent=agent, write_id=write_id, existed=existed)
        return existed

    def personal(self, agent: str) -> list[Listed]:
        """The owner's view: everything in `agent`'s personal sets, plain and by class, as kept. Needs
        capability `list_by_label_set`."""
        if not self.store.capabilities.list_by_label_set:
            raise NotImplementedError("this store cannot list by label set")
        out: list[Listed] = []
        for ls, partition in self.core.personal_sets(agent):
            out += self.store.list(partition, ls)
        _event("personal_listed", agent=agent, items=len(out))
        return out

    def stats(self, agent: str | None = None) -> dict:
        """Counts and timestamps for an operator or owner: per partition, and per personal set of `agent`
        in the partition that holds it. Needs capability `stats`."""
        if not self.store.capabilities.stats:
            raise NotImplementedError("this store has no stats")
        sets = self.core.personal_sets(agent) if agent else []
        return {p: self.store.stats(p, [ls for ls, part in sets if part == p] or None) for p in self.core.partitions()}


class AsyncMemory:
    """`Memory` for asyncio hosts: the same decisions, awaiting the store. The store may be an
    `AsyncStore` (every method a coroutine) or a synchronous `Store`, which is run in a thread."""

    def __init__(self, gate: Gate, store, shared: str, provenance: ProvenanceLog | None = None):
        self.core, self.store = Core(gate, shared, provenance), store
        self.gate = gate
        self._async = asyncio.iscoroutinefunction(getattr(store, "search", None))

    @property
    def capabilities(self) -> Capabilities:
        return self.store.capabilities

    async def _s(self, method: str, *args, **kwargs):
        fn = getattr(self.store, method)
        return await fn(*args, **kwargs) if self._async else await asyncio.to_thread(fn, *args, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def aclose(self) -> None:
        close = getattr(self.store, "aclose", None) or getattr(self.store, "close", None)
        if close:
            r = close()
            if asyncio.iscoroutine(r):
                await r

    async def create_bank(self) -> None:
        await self._s("ensure", self.core.shared)

    async def _keep(self, agent, location, labels, text, when, about, kind, turns=(), derived_from=(), key=None) -> str:
        item = self.core.plan_write(agent, location, labels, text, when, about, key)
        await self._s("ensure", item.partition, consolidate=item.consolidate)
        await self._s("put", item, agent=agent, location=location)
        self.core.record_write(agent, location, item, kind, turns, derived_from)
        return item.write_id

    async def remember(self, ctx: Context, text: str, *, when: datetime | None = None, about: str | None = None,
                       turns: list[str] = (), key: str | None = None) -> str:
        """See `Memory.remember`."""
        return await self._keep(ctx.agent, ctx.location, ctx.conversation(), text, when, about, "conversation", turns=turns, key=key)

    async def keep_note(self, ctx: Context, text: str, *, when: datetime | None = None, key: str | None = None) -> str:
        """See `Memory.keep_note`."""
        return await self._keep(ctx.agent, ctx.location, personal_note_labels(ctx.agent, ctx.location), text, when,
                                "personal note", "note", key=key)

    async def carry_out(self, ctx: Context, text: str, memory_type: str, *,
                        source: LabelSet | Recalled | str | None = None, when: datetime | None = None,
                        source_writes: list[str] = (), key: str | None = None, cls: str | None = None) -> str:
        """See `Memory.carry_out`."""
        writes = self.core.plan_carry_out(ctx, memory_type, source, source_writes, cls)
        return await self._keep(ctx.agent, ctx.location, personal_labels(ctx.agent, cls), text, when,
                                f"carried out ({memory_type})", "carry_out", derived_from=writes, key=key)

    async def say(self, ctx: Context, text: str, recalls: list[str] = ()) -> str | None:
        """See `Memory.say`."""
        return self.core.say(ctx, text, recalls)

    async def recall(self, ctx: Context, query: str, k: int = 20, **store_options) -> RecallBatch:
        """See `Memory.recall`."""
        allowed, partitions = self.core.plan_recall(ctx)
        for p in partitions:
            await self._s("ensure", p)
        hits = await self._s("search", partitions, query, allowed, k, agent=ctx.agent, location=ctx.location, **store_options)
        return self.core.finish_recall(ctx, query, allowed, hits, k)

    async def pending_operations(self) -> int:
        """See `Memory.pending_operations`."""
        return await self._s("pending", self.core.partitions())

    async def forget(self, agent: str, write_id: str) -> bool:
        """See `Memory.forget`."""
        if not self.store.capabilities.delete:
            raise NotImplementedError("this store cannot delete")
        self.core.owned_by(agent, write_id)
        existed = await self._s("delete", self.core.partition_of_write(write_id), write_id)
        _event("forget", agent=agent, write_id=write_id, existed=existed)
        if self.core.provenance:
            self.core.provenance.audit(None, "forget", agent=agent, write_id=write_id, existed=existed)
        return existed

    async def personal(self, agent: str) -> list[Listed]:
        """See `Memory.personal`."""
        if not self.store.capabilities.list_by_label_set:
            raise NotImplementedError("this store cannot list by label set")
        out: list[Listed] = []
        for ls, partition in self.core.personal_sets(agent):
            out += await self._s("list", partition, ls)
        return out

    async def stats(self, agent: str | None = None) -> dict:
        """See `Memory.stats`."""
        if not self.store.capabilities.stats:
            raise NotImplementedError("this store has no stats")
        sets = self.core.personal_sets(agent) if agent else []
        return {p: await self._s("stats", p, [ls for ls, part in sets if part == p] or None) for p in self.core.partitions()}
