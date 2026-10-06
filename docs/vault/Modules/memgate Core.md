---
type: module
status: active
authority: describes
summary: "memgate's system-agnostic core: labels and content-addressed label sets, the world model (environments, locations, high assurance), the label-set registry, Cedar schema and policies, the allowed-ID resolver and carry-out check, and derivation rules. 19 tests."
created: 2026-09-29
updated: 2026-09-30
tags: [module, memgate, permissions]
---

# memgate Core

> [!abstract] Role
> Decides what a context may recall and carry out, and how new and derived memories are labelled. Independent of any memory system. Design: [[Permission Layer]].

## Pieces

- **Decisions and the API** (`memgate/src/memgate/core.py`, since 0.6.0; see [[Store Protocol]]). `Core` makes every decision with no I/O: `plan_write` (may_write, register, `write_id_for`, `partition_for`, whether the class consolidates), `plan_carry_out` (may_carry_out plus the two class rules), `plan_recall` and `finish_recall` (the client-side filter over whatever the store returned, sorted by score), `say`, `owned_by`, `personal_sets` and `partitions_of_write` serve the owner's operations; since 0.6.2 a class set the world keeps out of consolidation is looked for in its class partition and in the shared one (`partitions_holding`), because items carried in before the flag was set live there and recall finds them. `Memory` and `AsyncMemory` put a `Store` behind it: `remember`, `keep_note`, `carry_out`, `say`, `recall`, `pending_operations`, and the host-trusted `forget`, `personal` and `stats`. Every event (write, recall, refused, forget) is one JSON line on the logger `memgate`, never with text.
- **The store protocol** (`memgate/src/memgate/store.py`): `Store` (`ensure`, `put`, `search`, `pending`, and the optional `delete`, `list`, `stats`), `Capabilities`, and the records `Item`, `Hit`, `Listed`.
- **Labels** (`memgate/src/memgate/labels.py`).
  - `Label` has four kinds: self, loc, with and (since 0.5.0) class. A class label is allowed only beside a self label, at most one per `LabelSet`, with a value from the ordered list `CLASSES` (`class_rank`, `strictest`); `LabelSet.classes` reads it. The policies never see it: it only makes a separate personal label set, so the memory system keeps classed personal memory apart.
  - A `LabelSet`'s `id` is a content-addressed hash, so every store and process agrees on it without coordination.
  - `NOBODY` is a participant no agent holds. It marks a derived memory whose sources share no participant.
- **World** (`memgate/src/memgate/world.py`).
  - `World` holds environments, locations and agents.
  - `Environment` lists the memory types that may be carried out: all (open), some (selective) or none (*Severance*).
  - `Location` can be high-assurance.
  - `carry_out_types` gives the types every location in a set allows.
  - An `Environment` may set `min_class` (since 0.5.0); `World.min_class` gives the strictest among some locations' environments. The client refuses a carry-out below it; it never chooses a class.
  - `ClassPolicy` (since 0.6.0): the world file's `classes` list; `World.consolidates(cls)` is False for a class marked `consolidate: false`, whose personal sets then live in a partition of their own (`class_bank`) with the store's consolidation off.
- **Registry** (`memgate/src/memgate/registry.py`): `Registry` is a SQLite table of every label set in use (or, given a `postgresql://` URL, `PostgresRegistry` in a `memgate` schema with registrations serialised by an advisory lock, since 0.6.0; `copy_from` migrates), and `register` is idempotent. It also keeps one indexed row per label (a `label` table, backfilled for older registries). `select_ids` runs a compiled filter, optionally only over label sets registered after a given row: the registry is append-only. Since 0.5.0, a label set holding a kind or class this version doesn't know (written by a newer memgate) is left out of `select_ids` and of `Registry.all`, so it is never readable or writable here and the rest keeps working; 0.4.x instead raised on such a row in `Registry.all`, which its validator calls on every write.
- **Policies** (`memgate/src/memgate/policies/memgate.cedar` and `memgate.cedarschema`):
  - read: identity and location labels held, and the reader among the participants;
  - the high-assurance seal;
  - write (since 2026-09-30): the writer holds every identity label and is the owner or a participant, a label set with a location is written only there, and the **high-assurance write seal**: anything written in a high-assurance location carries its label;
  - carry-out only where the source is readable, only as far as every environment allows, and never out of high assurance.
  - Derived attributes (`haLocs`, `carryTypes`) are computed from the world on every decision, because Cedar can't loop over set members.
- **Decisions** (`memgate/src/memgate/policy.py`):
  - `Policy.allowed_ids` returns the label sets a context may read, in four steps:
    1. Cedar partially evaluates the policies with the agent and location known and the label set unknown.
    2. `Compiler` (`memgate/src/memgate/residual.py`) turns the residual into one SQL filter over the registry. It handles the operators our policies use; anything else raises `Unsupported` and falls back to `Policy.allowed_ids_exact`, which checks each label set with Cedar.
    3. The result is cached per agent and location, keyed on `World.fingerprint`, and later calls check only label sets registered since.
    4. `memgate/tests/test_residual.py` checks the compiled answer against Cedar's exact answer for every agent and location in 300 random worlds, with and without an over-broad grant.
  - `Policy.may_write` decides every write (agent, location, label set); memgate's client and the validator both call it.
  - Every decision fails closed on an agent or location the world doesn't list (`Policy._known`): Cedar skips a policy that errors, and a skipped forbid would allow.
- **Deployment** (`Gate` in `memgate/src/memgate/context.py`): the world, registry and secret. Given the world file's path, `Gate.refresh` reloads it when it changes (checked at most once a second), so a running simulation can change agents, locations and environments without a restart; an unreadable file keeps the last good world.
  - `Policy.may_carry_out` checks a carry-out into personal memory, from the carrier's current location.
  - `Policy.validate` checks the policies against the schema.
- **Derivation** (`memgate/src/memgate/derivation.py`):
  - `conversation_labels` gives the location plus everyone present; `personal_labels` and `personal_note_labels` cover personal memory; `personal_labels(agent, cls)` gives the class set {self:A, class:C}.
  - `derived_labels` combines identity and location labels, intersects participants, and keeps the strictest class.
  - `check_merge` raises `CrossLabelSetMerge` if a merge would cross label sets.

- **Provenance and audit** (`memgate/src/memgate/provenance.py`), following the W3C PROV data model:
  - **The model:**
    - a memory write is an entity;
    - a recall is an activity that *used* the memories it returned;
    - a turn is an activity *informed by* recalls;
    - a memory was *generated by* turns, or *derived from* other memories;
    - agents are *associated with* activities.
  - **Recording:** `ProvenanceLog` records via `record_recall`, `record_turn`, `record_write` and `audit`. A write ID recorded again (a keyed write re-sent, 0.4.1) replaces its entity row and its source edges; what was built from it still points at it. `write_id_for` and `write_id_label_set` define the write-ID form shared with the validator.
  - **Storage:** SQLite (WAL, synchronous NORMAL), one file per partition, with PROV-named tables and indexed edge tables.
  - **Lineage is written at write time:** a `lineage` table holds each memory's direct sources, including those reached through its turns' recalls, indexed both ways.
  - **Walks visit each memory once,** level by level, so the cost grows with the memories reached, not the paths. A first version walked paths with a recursive query and took 21.6 s at depth 10.
  - **Queries:**
    - `sources_of`: one step back;
    - `ancestors`: where from;
    - `descendants`: impact, for retraction;
    - `exposure`: what an agent was shown, per label set;
    - `flows`: who recalled a label set, and what was built from it in other label sets. This is the leak audit;
    - `trail`: a memory's trail shown to an asker under the recall rules. Readable sources in full; unreadable ones as existence only, with nothing of what they were built from; unreadable high-assurance sources left out;
    - `export_prov`: W3C PROV-JSON, without memory text unless asked.
  - **Partitioned like memory:** each high-assurance location keeps its own file (`partition`). Nothing recorded there reaches the shared file, and queries from inside attach the shared file read-only.
- **Provenance speed** (`memgate/scripts/bench_provenance.py`, 2026-09-29, synthetic world: 100 agents, 8 rooms, 20 recalls per turn):

  | Turns | Link rows / size | Recording | One step | Ancestry depth 3 / 10 | Impact depth 3 | Exposure | Flows | Trail for an asker |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 10k | 263k / 43 MB | 4,100 events/s | 0.3 ms | 4 / 87 ms | 15 ms | 3 ms | 123 ms | 0.8 s |
  | 100k | 2.6M / 411 MB | 2,600 events/s | 0.3 ms | 4 / 167 ms | 22 ms | 34 ms | 351 ms | **7.9 s** |

  **The trail's cost was `Policy.allowed_ids`, not the log.** It checked every registered label set through Cedar, and random 2–4-agent groups gave 88,670 label sets.

  **Fixed the same day with the compiled filter and cache.** At 100k turns the trail now takes **11 ms**, down from 7.9 s. `Policy.allowed_ids` at 100k label sets:

  | Method | Time |
  | --- | --- |
  | Exact (Cedar per label set) | 8.9 s |
  | Compiled, first call | 86–120 ms |
  | **Compiled, cached (later calls)** | **0.01 ms** |

  The compiled answer is identical to Cedar's at every size.

## Tests (52 in memgate's environment, plus 27 validator specs in Hindsight's)

`memgate/tests/`:
- **Recall:**
  - only witnesses recall a conversation, and only in its location;
  - personal memory is readable by its owner everywhere and by no one else;
  - high assurance is outbound only;
  - Gus's {A,B}, {A,C}, then {A,B,C} case.
- **Carry-out:** open, selective and *Severance* environments; never out of high assurance; only a witness can carry a memory out; only where the source is readable.
- **Writes:** only a participant writes a conversation, only there; never under another agent's identity; notes only in their location; inside a high-assurance location, personal memory can't be written (the seal).
- **Derivation:** participants intersect; no shared participant means nobody can read it; a summary of {A,B} with {A,B,C} stays hidden from C; memories crossing locations are unreadable from either; merges only within a label set.
- **Schema:** the policies validate against the schema.
- **Entities** (`memgate/tests/test_entities.py`): `haLocs` and `carryTypes` mean what the proofs assume, on random worlds.
- **World reload** (`memgate/tests/test_world_reload.py`): a changed world file takes effect without a restart, decisions are recomputed, and a file that doesn't parse leaves the last good world in force.
- **Fail closed** (`memgate/tests/test_fail_closed.py`): unknown agents and locations are refused everything; an unreachable store raises rather than returning an unchecked answer; a refused write never reaches the store; a broken registry raises.
- **Validator spec** (`memgate/tests/test_validator.py`): every hook, including partition placement and the seal.
- **Negative controls:** removing the participant check lets a non-witness read. Removing the seal leaks the vault once an over-broad grant exists. The read rule alone already keeps high-assurance memories in place; the seal is the backstop for later rules that grant too much.

## Not yet

- **Verified context** (who is calling, where, with whom) is deferred to the Ranch integration; memgate trusts the context it's given ([[Trust Boundaries]]). Recall, write and carry-out decisions are all in Cedar and proved ([[memgate Proofs]]).
- **Provenance and audit are built** (2026-09-29) and wired into [[memgate Hindsight Adapter]].
