---
type: module
status: active
authority: describes
summary: "memgate's system-agnostic core: labels and content-addressed label sets, the world model (environments, locations, high assurance), the label-set registry, Cedar schema and policies, the allowed-ID resolver and carry-out check, and derivation rules. 19 tests."
created: 2026-09-29
updated: 2026-09-29
tags: [module, memgate, permissions]
---

# memgate Core

> [!abstract] Role
> Decides what a context may recall and carry out, and how new and derived memories are labelled. Independent of any memory system. Design: [[Permission Layer]].

## Pieces

- **Labels** (`memgate/src/memgate/labels.py`).
  - `Label` has three kinds: self, loc and with.
  - A `LabelSet`'s `id` is a content-addressed hash, so every store and process agrees on it without coordination.
  - `NOBODY` is a participant no agent holds. It marks a derived memory whose sources share no participant.
- **World** (`memgate/src/memgate/world.py`).
  - `World` holds environments, locations and agents.
  - `Environment` lists the memory types that may be carried out: all (open), some (selective) or none (*Severance*).
  - `Location` can be high-assurance.
  - `carry_out_types` gives the types every location in a set allows.
- **Registry** (`memgate/src/memgate/registry.py`): `Registry` is a SQLite table of every label set in use, and `register` is idempotent.
- **Policies** (`memgate/src/memgate/policies/memgate.cedar` and `memgate.cedarschema`):
  - read: identity and location labels held, and the reader among the participants;
  - the high-assurance seal;
  - carry-out only as far as every environment allows, and never out of high assurance.
  - Derived attributes (`haLocs`, `carryTypes`) are computed from the world on every decision, because Cedar can't loop over set members.
- **Decisions** (`memgate/src/memgate/policy.py`):
  - `Policy.allowed_ids` checks every registered label set in one Cedar batch and returns the IDs a context may read.
  - `Policy.may_carry_out` checks a write into personal memory.
  - `Policy.validate` checks the policies against the schema.
- **Derivation** (`memgate/src/memgate/derivation.py`):
  - `conversation_labels` gives the location plus everyone present; `personal_labels` and `personal_note_labels` cover personal memory.
  - `derived_labels` combines identity and location labels and intersects participants.
  - `check_merge` raises `CrossLabelSetMerge` if a merge would cross label sets.

## Tests (19)

`memgate/tests/`:
- **Recall:**
  - only witnesses recall a conversation, and only in its location;
  - personal memory is readable by its owner everywhere and by no one else;
  - high assurance is outbound only;
  - Gus's {A,B}, {A,C}, then {A,B,C} case.
- **Carry-out:** open, selective and *Severance* environments; never out of high assurance; only a witness can carry a memory out.
- **Derivation:** participants intersect; no shared participant means nobody can read it; a summary of {A,B} with {A,B,C} stays hidden from C; memories crossing locations are unreadable from either; merges only within a label set.
- **Schema:** the policies validate against the schema.
- **Negative controls:** removing the participant check lets a non-witness read. Removing the seal leaks the vault once an over-broad grant exists. The read rule alone already keeps high-assurance memories in place; the seal is the backstop for later rules that grant too much.

## Not yet

- **The allowed-ID resolver checks every label set.** Compiling Cedar's residual into a registry query waits until the label-set count needs it.
- **The SMT proof of the seal** needs the Cedar CLI with its analysis feature, plus cvc5; neither is installed yet.
- **Provenance log, audit, and the Hindsight adapter** are next.
