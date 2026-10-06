"""The store protocol: what memgate needs from a memory system, and what it may optionally offer.

memgate's decisions (memgate.core) are store-agnostic: who may read which label sets where, what label
set a write gets, which partition it belongs in, whether a carry-out is allowed, and what to record. A
store does the keeping and the searching. It sees only opaque label-set IDs (as tags, scopes or whatever
it has), partition keys, write IDs and text. This module is the seam between the two.

A store declares its `Capabilities`. Everything memgate guarantees with every store rests on the client
side of the decisions; what a store adds (a second lock inside the store, idempotent replace by write ID,
separate partitions, deletion, listing) is a capability, and `memgate conformance` checks only what the
store claims. The integration guide's capability table comes from these flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Capabilities:
    second_lock: bool = False        # the store re-derives and enforces the allowed label sets itself (Hindsight's validator)
    idempotent_replace: bool = False  # a put with a known write ID replaces the earlier item instead of adding one
    partitions: bool = False          # separate storage per partition key, searched only when asked (high assurance)
    delete: bool = False              # delete by write ID, taking derived items with it
    list_by_label_set: bool = False   # list the items of a label set (owner views, conformance's class-apart)
    stats: bool = False               # counts and timestamps per partition (observability)
    consolidation_control: bool = False  # consolidation can be turned off per partition


@dataclass
class Item:
    """One thing to keep: the text and what memgate decided about it."""
    text: str
    label_set: str                   # the registered label-set ID; the store's tag or scope
    write_id: str                    # memgate's write ID (w_<label set>_<16 hex>); the store's document or memory ID
    partition: str                   # which partition holds it (the shared one, or a high-assurance location's)
    when: datetime | None = None
    about: str | None = None         # a short description for the store's extraction, if it has one
    consolidate: bool = True         # False for a label set whose class is kept out of consolidation


@dataclass
class Hit:
    """One recalled memory, as every store must return it."""
    text: str
    label_set: str
    when: str | None = None          # ISO date (first ten characters) or None
    write_id: str | None = None
    score: float = 0.0               # higher is better; 0.0 everywhere means "keep the store's own order"


@dataclass
class Listed:
    """One stored item, as an owner view or conformance sees it."""
    write_id: str
    label_set: str
    text: str
    when: str | None = None          # month precision (YYYY-MM): the owner's view shows no exact dates
    kind: str = "memory"             # "memory" (a stored write) or "derived" (built by the store from others)
    sources: list[str] = field(default_factory=list)   # write IDs a derived item was built from, when known


@runtime_checkable
class Store(Protocol):
    """A memory system under memgate. Required: `ensure`, `put`, `search`, `pending`. The rest only when
    the matching capability is claimed; memgate never calls them otherwise."""

    capabilities: Capabilities

    def ensure(self, partition: str, *, consolidate: bool = True) -> None:
        """Make the partition exist (idempotent); with `consolidate` False, keep consolidation off in it."""

    def put(self, item: Item, *, agent: str | None, location: str | None) -> None:
        """Keep one item. `agent` and `location` are the acting context, for a store with a second lock."""

    def search(self, partitions: list[str], query: str, allowed: set[str], k: int, *,
               agent: str | None, location: str | None) -> list[Hit]:
        """Up to `k` memories per partition whose label set is in `allowed`, scored higher-is-better (a store
        may size by its own budget instead of `k`; memgate cuts to `k` after merging partitions). A store
        without a second lock must apply `allowed` itself and return nothing else; one with a second lock
        may pass it as a hint, since it re-derives the set. A hit without a label set is never shown."""

    def pending(self, partitions: list[str]) -> int:
        """Background work not yet finished (extraction, consolidation); 0 for a synchronous store."""

    def delete(self, partition: str, write_id: str) -> bool:
        """Capability `delete`: remove the item and whatever the store derived from it. True if it existed."""

    def list(self, partition: str, label_set: str) -> list[Listed]:
        """Capability `list_by_label_set`: every stored item of one label set, derived ones included."""

    def stats(self, partition: str, label_sets: list[str] | None = None) -> dict:
        """Capability `stats`: counts and timestamps for the partition, per label set when given."""
