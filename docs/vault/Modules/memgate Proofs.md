---
type: module
status: active
authority: describes
summary: "Formal proofs of memgate's Cedar policies with Cedar's symbolic compiler (SymCC, checked in Lean, solved by cvc5): for every possible request and entity store, recall, writes and carry-out are each allowed exactly when their stated rules hold, including the high-assurance seal on reads and writes. All six policies never error, for any of the three actions. One guarantee depends on memgate computing haLocs correctly, which a Python test checks."
created: 2026-09-30
updated: 2026-09-30
tags: [module, memgate, security, formal-methods]
---

# memgate Proofs

> [!abstract] Role
> Proves what the policies in [[memgate Core]] guarantee, for *every* request, not just the ones a benchmark happens to try. It complements the [[Selective Memory Benchmark]], which tests the whole system on sample worlds. The two together are the evidence in [[Trust Boundaries]] for the policy layer.

Code: `memgate/proofs/src/main.rs`, a small Rust crate (cedar-policy 4.13.0, cedar-policy-symcc 0.7.0), reading `memgate/src/memgate/policies/memgate.cedar` and its schema. Results: `memgate/proofs/results.json`.

    cd memgate/proofs && CVC5=$PWD/../.tools/cvc5-macOS-arm64-static/bin/cvc5 cargo run --release

Rust comes from Homebrew. The cvc5 solver 1.4.1 lives in `memgate/.tools/`, which is gitignored. Download it from the cvc5 GitHub releases.

## How it works

Each guarantee is written as a Cedar *property* policy. SymCC compiles memgate's policies and the property to SMT and asks cvc5 whether any request and entity store tells them apart:
- **Implies:** whatever memgate allows, the property allows.
- **Equivalent:** they allow exactly the same requests.
- **Not always-denies:** memgate allows something (so it isn't safe by being useless).

A failure comes with a concrete counterexample, a request plus entities. Separately, every policy is checked never to error. Cedar skips a policy that errors, and for a forbid that would mean *allowing*.

## Results (2026-10-06, with the source seal)

| Property | Claim | Result |
| --- | --- | --- |
| never-errors | None of the eight policies errors, for any of the three actions | proved (24/24) |
| R1 identity | A memory with an identity label is recalled only by that agent | proved |
| R2 location | A memory with a location label is recalled only in that location | proved |
| R3 participants | A memory with participant labels is recalled only by a participant | proved |
| R4 seal | A memory formed in a high-assurance location is recalled only there | proved |
| R5 seal by location | Outside a high-assurance location, nothing formed in one is recalled | depends on an invariant (below) |
| R8 source seal (0.7.0) | A memory carried out of a location that now lets nothing out is recalled only in that location | proved |
| R9 source seal by world (0.7.0) | Outside such a location, nothing carried out of it is recalled, given that `sealedSrcs` is computed from the world (tested, below) | proved |
| R6 read spec | Recall is allowed **exactly** when R1–R4 and R8 hold: no other way in, nothing permitted refused | proved |
| R7 read live | Some recall is allowed | proved |
| C1 no high assurance | Nothing formed in a high-assurance location is carried out | proved |
| C2 environments allow | Carried out only if every source environment lets that type out | proved (meaning depends on carryTypes) |
| C3 carrier had access | Only an agent holding the identity and participant labels can carry it out | proved |
| C4 carry where readable | A memory is carried out only where its source is readable (added 2026-09-30) | proved |
| C5 carry spec | Carry-out is allowed **exactly** when C1–C4 hold | proved |
| C6 carry live | Some carry-out is allowed | proved |
| W1 own identity | No agent writes under another agent's identity label | proved |
| W2 writer holds | A writer writes under its own identity or is a participant | proved |
| W3 write place | A memory with a location label is written only in that location | proved |
| W4 write seal | Anything written in a high-assurance location carries that location's label | proved |
| W7 write source (0.7.0) | A memory with a source label is written only in that source location | proved |
| W5 write spec | A write is allowed **exactly** when W1–W4 and W7 hold | proved |
| W6 write live | Some write is allowed | proved |

## What the proofs rest on

- **Attributes computed in Python.** Cedar can't loop over a set's members. So memgate precomputes attributes per label set in `Policy._label_set_entity`:
  - `haLocs`: the high-assurance locations among its locations;
  - `carryTypes`: the memory types every location's environment lets out;
  - `sealedSrcs` (0.7.0): the sources among its labels whose environment currently lets nothing out (`World.sealed`), the attribute the source seal reads.

  SymCC treats these as arbitrary. That's why R5 gets a counterexample: a label set whose `haLocs` names a location that isn't high-assurance, and why R9 assumes its `sealedSrcs`. `memgate/tests/test_entities.py` and `memgate/tests/test_source_seal.py` check, on random worlds, that the attributes are computed exactly as the proofs assume. With them, R5, R9 and C2 hold end to end.
- **Every agent and location exists.** SymCC assumes the entities a request names exist. memgate refuses any decision about an agent or location the world doesn't list (`Policy._known`), so that assumption always holds; without the guard, a missing location would make the write seal error, and Cedar skips an erroring forbid.
- **The inputs to a decision.** A proof covers the decision for a given request: agent, location, label set, memory type. It says nothing about whether those inputs are true. Who supplies them, and how far each is trusted, is the subject of [[Trust Boundaries]].
- **The seal, end to end.** W4 (a write in a high-assurance location carries its label), the tested `haLocs` invariant, and R4 (a memory with a high-assurance label is recalled only there) together give: nothing written inside a high-assurance location is ever recalled outside it.
- **The source seal, end to end (0.7.0).** `Core.carry_out` files every carry-out under a set whose `src` is the Context's location; W7 (a sourced set is written only at its source, so the label is true wherever the write came through either lock); the tested `sealedSrcs` invariant; and R8 (a memory whose source now lets nothing out is recalled only there) together give: once a location's environment is set to `carry_out: []`, nothing carried out of it is recalled anywhere else, and derived items follow because derivation never crosses label sets. Reversible by the world file alone. Items kept before 0.7.0 carry no source and are outside this.
- **Classes are outside the policies (0.5.0).** `Policy._label_set_entity` gives Cedar no class attribute, so a class set {self:A, class:C} is decided exactly as {self:A} and no proof changes. What a class is for, keeping classed personal memory from being consolidated with the rest, rests on the memory system's per-tag consolidation and on two client-side carry-out rules (`Core.plan_carry_out` in `memgate/src/memgate/core.py`, since 0.6.0; before that inside the Hindsight adapter). Neither is proved; conformance checks the first live (`class-apart`) and tests the second.
- **Only the policies.** Label derivation (`memgate/src/memgate/derivation.py`) and the SQL compilation of the read policies are Python, covered by tests (the compiled filter against Cedar in `memgate/tests/test_residual.py`), not by these proofs. Every write and carry-out decision is a Cedar call (`Policy.may_write`, `Policy.may_carry_out`), made by memgate's client and again by the validator (`MemgateValidator.validate_retain`).
