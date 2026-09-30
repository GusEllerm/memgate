---
type: module
status: active
authority: describes
summary: "Formal proofs of memgate's Cedar policies with Cedar's symbolic compiler (SymCC, checked in Lean, solved by cvc5): for every possible request and entity store, recall is allowed exactly when the identity, location, participant and high-assurance rules all hold, and carry-out exactly when its three rules hold. All eight policy checks never error. One guarantee depends on memgate computing haLocs correctly, which a Python test checks."
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

## Results (2026-09-30)

| Property | Claim | Result |
| --- | --- | --- |
| never-errors | None of the four policies errors, for either action | proved (8/8) |
| R1 identity | A memory with an identity label is recalled only by that agent | proved |
| R2 location | A memory with a location label is recalled only in that location | proved |
| R3 participants | A memory with participant labels is recalled only by a participant | proved |
| R4 seal | A memory formed in a high-assurance location is recalled only there | proved |
| R5 seal by location | Outside a high-assurance location, nothing formed in one is recalled | depends on an invariant (below) |
| R6 read spec | Recall is allowed **exactly** when R1–R4 hold: no other way in, nothing permitted refused | proved |
| R7 read live | Some recall is allowed | proved |
| C1 no high assurance | Nothing formed in a high-assurance location is carried out | proved |
| C2 environments allow | Carried out only if every source environment lets that type out | proved (meaning depends on carryTypes) |
| C3 carrier had access | Only an agent holding the identity and participant labels can carry it out | proved |
| C4 carry spec | Carry-out is allowed **exactly** when C1–C3 hold | proved |
| C5 carry live | Some carry-out is allowed | proved |

## What the proofs rest on

- **Attributes computed in Python.** Cedar can't loop over a set's members. So memgate precomputes two attributes per label set in `Policy._label_set_entity`:
  - `haLocs`: the high-assurance locations among its locations;
  - `carryTypes`: the memory types every location's environment lets out.

  SymCC treats these as arbitrary. That's why R5 gets a counterexample: a label set whose `haLocs` names a location that isn't high-assurance. `memgate/tests/test_entities.py` checks, on random worlds, that the attributes are computed exactly as the proofs assume. With it, R5 and C2 hold end to end.
- **The inputs to a decision.** A proof covers the decision for a given request: agent, location, label set, memory type. It says nothing about whether those inputs are true. Who supplies them, and how far each is trusted, is the subject of [[Trust Boundaries]].
- **Only the policies.** Label derivation (`memgate/src/memgate/derivation.py`), the write checks in the validator (`MemgateValidator.validate_retain`) and the SQL compilation of the policies are Python. They are covered by tests (the compiled filter against Cedar in `memgate/tests/test_residual.py`), not by these proofs. Moving write authorisation into Cedar would bring it under the proofs too; see [[Trust Boundaries]].
