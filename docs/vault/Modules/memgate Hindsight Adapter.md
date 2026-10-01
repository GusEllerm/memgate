---
type: module
status: active
authority: describes
summary: "memgate's Hindsight adapter: a client that labels, registers and tags every write and scopes every recall (first lock), and an operation-validator extension inside Hindsight that recomputes and overwrites recall tags, checks writes, and closes the side doors (second lock). 9 live integration tests pass, including bypass attempts, the high-assurance write seal and partition placement; 27 spec tests call every validator hook directly (`memgate/tests/test_validator.py`, run in Hindsight's environment)."
created: 2026-09-29
updated: 2026-09-30
tags: [module, memgate, hindsight]
---

# memgate Hindsight Adapter

> [!abstract] Role
> Level A adapter ([[Permission Layer]]): Hindsight stores a label-set ID as each item's only tag, and its recall filters by the allowed IDs inside the search.

## Client: the first lock

Code: `memgate/src/memgate/adapters/hindsight/client.py`.

`HindsightMemory` (synchronous, urllib) and `AsyncHindsightMemory` (asyncio, httpx; since 0.3.0) are the only way agents' memory reaches Hindsight. They have the same API. Both are built on `_Core`, which makes every decision (labels, permission checks, routing, provenance) and does no I/O. So the two cannot decide differently; only the transport differs. Their operations are below.

**Partitions (since 2026-09-30).** A world has one shared bank, for ordinary locations and personal memory, plus one bank per high-assurance location, named by `partition_bank` in `memgate/src/memgate/context.py`. `_Core.bank_for` sends each write to the partition of the high-assurance location it is labelled with, if any. A recall in a high-assurance location searches its partition and the shared bank (where personal memory lives) and merges the two by Hindsight's final score. A recall anywhere else never touches a partition. So a vault's memories never share ranking statistics, caches or consolidation with anything outside it. `_Core.partitions` lists the banks, and `HindsightMemory.pending_operations` counts across all of them.

**Transport (since 0.4.0).** A server address is `http://host:port` or `unix:/path/memgate.sock`, sent through `send` in `memgate/src/memgate/adapters/hindsight/client.py`, never through a proxy. Over a socket, `check_socket` first refuses a socket whose directory isn't private (0700) and owned by this user. That is how the server proves who it is: nothing else could be listening there to collect the secret, whereas over a port a squatter could. `memgate serve --socket` serves Hindsight's ASGI app under uvicorn `--uds`, with no TCP port.

**A separate partition server (since 0.3.0).** With `partition_url=`, every call on a partition bank goes to its own server (`_Core._base_for`), and everything else to `base_url`. Run that server with `memgate serve --scope partitions` and the other with `--scope shared`: the validator's `MemgateValidator._out_of_scope` then refuses the other's banks on each. It's for isolation; it's also the only way to give high assurance its own LLM, since Hindsight 0.10.1 can't set an LLM per bank.

Every method takes a `Context` (agent, location, participants; `memgate/src/memgate/context.py`), which the host builds from what it has verified; the acting agent is always among the participants (since 0.2.0, 2026-09-30).

| Method | Does |
| --- | --- |
| `HindsightMemory.remember` | Stores something from `ctx`'s conversation under its label set (location + participants) |
| `HindsightMemory.keep_note` | A personal note that stays where it was written |
| `HindsightMemory.carry_out` | Checks `Policy.may_carry_out` at `ctx`'s location, then writes into personal memory. The source is a recalled item (its label set, with its write as provenance; since 0.3.0), a label set or its ID, or by default `ctx`'s conversation (`Context.conversation`) |
| `HindsightMemory.say` | Records what the agent said to `ctx`'s participants and which recalls it drew on (provenance) |
| `HindsightMemory.recall` | Computes the allowed IDs itself and passes them as tags with `any_strict` |

Every request carries the gate secret plus the agent and location headers, from `memgate/src/memgate/context.py` (`Gate`, `load_world`).

**Provenance** (optional, when given a `ProvenanceLog`):
- **Writes:** every write is first checked with `Policy.may_write` (PermissionError if refused). Every write gets a write ID (`write_id_for`: `w_<label set ID>_<16 hex>`, since 0.4.1 carrying its label set), stored as Hindsight's document_id, so every fact Hindsight extracts from it traces back to it. The write and its sources are logged. With a caller `key` (`remember`/`keep_note`, since 0.4.1) the tail is a hash of the key, so the same key under the same label set re-sent gets the same write ID and replaces the earlier write (Hindsight upserts by document_id; the log replaces the row and its sources) instead of duplicating it: exactly-once storage for an at-least-once host.
- **Recalls:** `HindsightMemory.recall` returns a `RecallBatch`. Each `Recalled` item carries its `write_id`, and the batch carries the `recall_id` of the logged recall.
- **Turns:** `HindsightMemory.say` records what an agent said and which recalls it drew on. `HindsightMemory.remember(turns=...)` links a new memory to those turns.
- **Audit:** carry-outs, allowed or refused, are audited.

## Validator: the second lock, inside Hindsight

Code: `memgate/src/memgate/adapters/hindsight/validator.py`. `MemgateValidator` is loaded by Hindsight from HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION.

- **Fails closed:** an exception inside the validator fails the request. An unknown agent or location is refused (see `Policy` in [[memgate Core]]). The world file is re-read when it changes (`Gate.refresh`), with no restart.
- **Identity:** trusts only the caller's identity. A request without the memgate secret is refused, and Hindsight's own background work (consolidation) passes as internal.
- **`validate_recall`:** recomputes the allowed IDs with the same world and registry, and **overwrites** the request's tags. Forged tags are ignored. `Gate` keeps a single `Policy`, so the compiled per-context cache ([[memgate Core]]) survives across requests: a repeat recall costs about 0.01 ms at 100k label sets.
- **`validate_retain`:** each item needs exactly one registered label-set tag, and `Policy.may_write` must allow the writer to write it at its location (the same Cedar decision memgate's client makes first, including the high-assurance write seal). Observation scopes wider than "combined" are refused. Since 0.4.1 any `update_mode` is refused (an append would fold another document's text into this write and re-extract it under this write's label set), and a `document_id` must have been minted under the item's own label set (`write_id_label_set`), since Hindsight replaces the document that ID names: a reused ID can never erase or absorb another label set's memory. A memory labelled with a high-assurance location must go to that location's partition, and nothing else may (`partition_location`).
- **Partitions in recall:** a partition is searched only from inside its location; from anywhere else the recall is refused.
- **Side doors closed:**
  - reflect is refused, because its scope can't be enforced;
  - mental models are refused, because they blend a bank;
  - memory-reading bank operations (list, export, get document, entity graph, …) are refused for agents, via `validate_bank_read`;
  - bank writes and bank creation are admin-only (`validate_bank_write`, `validate_create_bank`).

**Launch:** `memgate serve` ([[memgate Integration]]) runs Hindsight with the validator loaded:
- its own database (pg0://memgate by default);
- port 8889, **bound to 127.0.0.1** (a non-loopback bind needs `--allow-remote`);
- the LLM-request log, audit log and tracing off.

In this repo, `memgate/scripts/serve_hindsight_gated.sh` wraps it with the repo's defaults (memgate/.run/, the ALCF gateway).

## Tests (live)

`memgate/tests/test_hindsight_integration.py` is skipped unless MEMGATE_HINDSIGHT_URL is set. It plants canary strings in conversations {A,B}, {A,C} and {A,B,C} in the lab, and {A,B} in the high-assurance vault. It also adds a personal note in the vault and an opinion carried out into personal memory. It checks:

- **Recall:**
  - Ada in the lab reaches {A,B}, {A,C}, {A,B,C} and her personal memory, but nothing from the vault.
  - Cy reaches {A,C} and {A,B,C} but not {A,B}.
  - Dee reaches nothing.
  - Ada in the cafe reaches only her personal memory.
  - Ada in the vault reaches the vault, her note and her personal memory.
- **Carry-out:** refused out of *Severance* and out of high assurance.
- **Bypass attempts:**
  - no secret: 403;
  - Dee forging the {A,B} tag: nothing returned;
  - reflect, list and export: 403;
  - writing to a label set you're not in, unlabelled, or with an unregistered tag: 403.

- **Retelling leaves a trail** (`test_retelling_leaves_a_trail`):
  - Ada recalls the {A,B} memory in front of Cy and retells it.
  - The {A,B,C} memory formed from that turn points back to it.
  - Ada can read that source; Cy sees only that it exists.

2026-09-29: **7 passed** (80 s).

## Known limits

- **Headers are trusted once the secret matches.** That's fine while memgate is the only caller. A multi-client deployment should map per-agent API keys to identity instead.
- **Hindsight's graph search arm** filters by tag after scoring. There's no leak, but recall may drop.
- **Consolidation** relies on Hindsight's default combined scope and on every item having exactly one label-set tag. Both are enforced at retain.
