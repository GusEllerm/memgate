---
type: module
status: active
authority: describes
summary: "memgate's Hindsight adapter: a client that labels, registers and tags every write and scopes every recall (first lock), and an operation-validator extension inside Hindsight that recomputes and overwrites recall tags, checks writes, and closes the side doors (second lock). 6 live integration tests pass, including bypass attempts."
created: 2026-09-29
updated: 2026-09-29
tags: [module, memgate, hindsight]
---

# memgate Hindsight Adapter

> [!abstract] Role
> Level A adapter ([[Permission Layer]]): Hindsight stores a label-set ID as each item's only tag, and its recall filters by the allowed IDs inside the search.

## Client: the first lock

Code: `memgate/src/memgate/adapters/hindsight/client.py`.

`HindsightMemory` is the only way agents' memory reaches Hindsight. One bank holds a world. Its operations:

| Method | Does |
| --- | --- |
| `HindsightMemory.remember` | Labels a conversation memory (location + participants), registers the label set, retains with it as the only tag |
| `HindsightMemory.keep_note` | A personal note that stays in its location |
| `HindsightMemory.carry_out` | Checks `Policy.may_carry_out`, then writes into personal memory |
| `HindsightMemory.recall` | Computes the allowed IDs itself and passes them as tags with `any_strict` |

Every request carries the gate secret plus the agent and location headers, from `memgate/src/memgate/context.py` (`Gate`, `load_world`).

**Provenance** (optional, when given a `ProvenanceLog`):
- **Writes:** every write gets a write ID, stored as Hindsight's document_id, so every fact Hindsight extracts from it traces back to it. The write and its sources are logged.
- **Recalls:** `HindsightMemory.recall` returns a `RecallBatch`. Each `Recalled` item carries its `write_id`, and the batch carries the `recall_id` of the logged recall.
- **Turns:** `HindsightMemory.say` records what an agent said and which recalls it drew on. `HindsightMemory.remember(turns=...)` links a new memory to those turns.
- **Audit:** carry-outs, allowed or refused, are audited.

## Validator: the second lock, inside Hindsight

Code: `memgate/src/memgate/adapters/hindsight/validator.py`. `MemgateValidator` is loaded by Hindsight from HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION.

- **Identity:** trusts only the caller's identity. A request without the memgate secret is refused, and Hindsight's own background work (consolidation) passes as internal.
- **`validate_recall`:** recomputes the allowed IDs with the same world and registry, and **overwrites** the request's tags. Forged tags are ignored.
- **`validate_retain`:** each item needs exactly one registered label-set tag that the writer may write (a participant or owner, in that location). Observation scopes wider than "combined" are refused.
- **Side doors closed:**
  - reflect is refused, because its scope can't be enforced;
  - mental models are refused, because they blend a bank;
  - memory-reading bank operations (list, export, get document, entity graph, …) are refused for agents, via `validate_bank_read`;
  - bank writes and bank creation are admin-only (`validate_bank_write`, `validate_create_bank`).

**Launch:** `memgate/scripts/serve_hindsight_gated.sh` runs Hindsight with the validator loaded:
- its own database (pg0://memgate);
- port 8889, **bound to 127.0.0.1**;
- the LLM-request log, audit log and tracing off.

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
