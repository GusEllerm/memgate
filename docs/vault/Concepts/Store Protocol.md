---
type: design
status: active
authority: describes
summary: "The seam between memgate's decisions and any memory system (memgate 0.6.0): a store-agnostic decision core, a small store protocol (ensure, put, search, pending) with optional capabilities (second lock, idempotent replace, partitions, delete, list by label set, stats, consolidation control), Hindsight and Mem0 as its two stores, and conformance that checks only what a store claims."
created: 2026-10-06
updated: 2026-10-06
tags: [memgate, design, adapters]
---

# Store Protocol

*Ruled by Gus 2026-10-06 ([[Decision Log]], "The adapter boundary"): refactor so the decisions no longer live inside the Hindsight adapter, and promote the benchmark's Mem0 adapter into memgate as the second store.*

**The idea.** The Cedar policies, the world, the registry and the label derivation never knew about Hindsight; the code that applied them did. Before 0.6.0 one class held the permission checks, the write-ID minting, the carry-out rules and the provenance calls together with Hindsight's request bodies, tag filters and bank routing, and the benchmark's Mem0 systems had to copy the decisions. 0.6.0 splits them.

## The three layers

- **Decisions** (`memgate/src/memgate/core.py`, `Core`): no I/O. `plan_write` checks `Policy.may_write`, registers the label set, mints the write ID (`write_id_for`) and chooses the partition (`partition_for`: a high-assurance location's own, else a non-consolidating class's own (`class_bank`), else the shared one), and asks the world whether the label set's class consolidates (`World.consolidates`). `plan_carry_out` runs `Policy.may_carry_out` and the two class rules. `plan_recall` gives the allowed label sets and the partitions to search; `finish_recall` keeps only hits whose label set is allowed (the client-side lock, whatever the store returned), orders them by score and records the recall. `owned_by` and `personal_sets` serve the owner's operations.
- **The store** (`memgate/src/memgate/store.py`): what a memory system must do and may offer. Required: `ensure`, `put`, `search`, `pending` (the Decision Log row's shorter list omitted `ensure`). Optional, each behind a flag in `Capabilities`: `second_lock`, `idempotent_replace`, `partitions`, `delete`, `list_by_label_set`, `stats`, `consolidation_control`. A store sees only opaque label-set IDs, partition keys, write IDs and text (`Item`, `Hit`, `Listed`); the owner-view fields `source` and `withheld` on `Listed` (0.7.0) are filled by the core, not the store.
- **The API** (`Memory`, `AsyncMemory` in `memgate/src/memgate/core.py`): `remember`, `keep_note`, `carry_out`, `say`, `recall`, `pending_operations`, and the host-trusted owner operations `forget`, `personal` and `stats`, each refused with `NotImplementedError` when the store lacks the capability. `AsyncMemory` takes an async store or runs a synchronous one in a thread.

## The two stores

| | Hindsight (`memgate/src/memgate/adapters/hindsight/store.py`) | Mem0 (`memgate/src/memgate/adapters/mem0/store.py`) |
| --- | --- | --- |
| Label set | a tag; recall with `any_strict` over the allowed ones | the `user_id` scope; recall with an OR over the allowed ones (ANDed with a constant `agent_id`, which Mem0 needs as a top-level key) |
| Partition | a bank; high-assurance locations get their own | none: one collection, kept apart by label set only |
| Second lock | `MemgateValidator` inside the server | none; the client is the only enforcement |
| Idempotent replace | `document_id` upsert | emulated: a put first removes what its write ID stored |
| Delete | a document and the observations built on it | the memories a write ID produced |
| List, stats | the admin listing filtered by tag; bank stats and operations | `get_all` by scope |
| Consolidation control | per bank (`enable_observations`, `enable_auto_consolidation`) | none to control |

`HindsightMemory` and `AsyncHindsightMemory` (`memgate/src/memgate/adapters/hindsight/client.py`) are `Memory` and `AsyncMemory` over the Hindsight store under the names hosts already use, with the same constructor, plus `check_version` (the handshake) and `_call` for tests and tools.

## What follows from the split

- **Conformance checks only what a store claims** (`memgate/src/memgate/conformance.py`): the validator probes need `second_lock` (and Hindsight, which is the only validator it knows how to probe), the partition checks `partitions`, `class-apart` and `owner-view` `list_by_label_set` (and `delete`). Everything else runs against the `Memory` API, so it is the same check on either store. On a store without partitions the canaries share the collection with real data, so cleanup deletes exactly the writes the run made.
- **The integration guide gets a capability table**, so a host knows which guarantees hold with which store. The proofs cover the decisions; the second lock and per-label-set consolidation are Hindsight properties.
- **New operations are designed against the protocol.** Forget, the owner listing and stats landed this way in 0.6.0, and the benchmark's Mem0 systems (`benchmark/src/smbench/selective/systems_mem0.py`) now wrap memgate's store rather than copying its logic.
