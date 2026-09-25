---
type: reference
status: active
authority: reference
summary: "Cedar (v4.13.0, Apache-2.0): our label rules fit in a few validated policies; partial evaluation leaves a residual that compiles to array operators and matched a brute-force run over 100k label sets in 0.03 s; the SMT analyzer can prove the high-assurance seal. Partial evaluation and the filter compiler are experimental or ours to write."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, policy-engine, cedar]
---

# Cedar

*Surveyed 2026-09-25 from [cedar-policy/cedar](https://github.com/cedar-policy/cedar) v4.13.0 (commit 324d3c0), its [changelog](https://raw.githubusercontent.com/cedar-policy/cedar/main/cedar-policy/CHANGELOG.md), the [OOPSLA 2024 paper](https://arxiv.org/abs/2403.04651), [RFC 95 on typed partial evaluation](https://github.com/cedar-policy/rfcs/blob/main/text/0095-type-aware-partial-evaluation.md), the [Cedar Analysis announcement](https://aws.amazon.com/blogs/opensource/introducing-cedar-analysis-open-source-tools-for-verifying-authorization-policies/) and the [operator docs](https://docs.cedarpolicy.com/policies/syntax-operators.html). The agent also ran experiments with cedarpy 4.12.1 on 100k synthetic label sets. Facts are as of that date. Listed in [[Architecture Survey]].*

**Interactive briefing:** [Cedar, in Practice](https://claude.ai/artifact/WU8MjZGLw6mb4qcdjHMpj4) covers Cedar's history and has eight editable example policies for our label model. They run in the browser on Cedar 4.13.0 (private artifact, 2026-09-25).

**Verdict so far.** A strong fit.
- **Expressiveness:** our read rule, the high-assurance seal and a *Severance* write rule fit in three short policies that pass validation.
- **Listing readable label sets:** partial evaluation, with the context known and the item left unknown, leaves a residual condition. That residual compiles straight into array operators. Run over a table of 100k label sets, it produced the same 3,070 allowed IDs as checking each set one by one, in 0.03 s instead of 4.9 s.
- **Proof:** Cedar's SMT analyzer can prove that no policy lets a high-assurance location's items be read outside it.
- **Caveats:** partial evaluation is experimental, and we would write the residual-to-filter compiler ourselves.

## What it is

- **Versions:** cedar-policy v4.13.0 and cedar-policy-symcc v0.7.0 (both 2026-09-15). Apache-2.0, actively maintained.
- **Adoption:** used by Amazon Verified Permissions and AgentCore. Listed as CNCF Sandbox (from a search snippet, not verified). AWS's Dogwood extends Cedar to sequences of agent actions, but loses analyzability.
- **Bindings, all in-process:**
  - Rust core.
  - WASM/JS, with partial evaluation.
  - Java (JNI), with partial evaluation.
  - Go, a separate pure-Go implementation with an experimental batch API.
  - Python (cedarpy, community-maintained), with batch and partial evaluation.

## Modelling our rules

Each label combination is a LabelSet entity whose attributes are sets of labels. The request context is a record. This sketch passes validation:

```
entity Agent; entity Location { highAssurance: Bool };
entity Environment { carryOut: Bool, personalWrites: Bool };
entity LabelSet = { selfs: Set<Agent>, locs: Set<Location>, withs: Set<Agent>, haLocs: Set<Location> };
action read appliesTo { principal: Agent, resource: LabelSet, context: { location: Location, present: Set<Agent> } };
action derive, writePersonal appliesTo { principal: Agent, resource: LabelSet, context: { env: Environment, target: LabelSet } };

permit(principal, action == Action::"read", resource)          // all of self and location, any participant
when { [principal].containsAll(resource.selfs)
    && [context.location].containsAll(resource.locs)
    && (resource.withs.isEmpty() || resource.withs.containsAny(context.present)) };
forbid(principal, action == Action::"read", resource)           // high-assurance seal
unless { [context.location].containsAll(resource.haLocs) };
forbid(principal, action in [Action::"derive", Action::"writePersonal"], resource)  // Severance
when { !context.env.carryOut && !(context.target.locs.containsAll(resource.locs)
                                 && context.target.withs.containsAll(resource.withs)) };
```

- **Forbid always overrides permit,** which suits seals.
- **No quantifiers over set members.** "Does this set include a high-assurance location?" must be precomputed (haLocs) when the label set is created.
- **Nested locations** can use Cedar's entity hierarchy.

## Listing readable label sets

| Approach | Result (100k label sets) | Status |
| --- | --- | --- |
| Check every label set (batch) | 4.9 s (about 49 µs each, mostly Python overhead), plus 2.3 s to load entities | Stable; too slow per query |
| Partial evaluation → residual → filter over the label-set table | Same 3,070 IDs in 0.03 s | Experimental; hand-compiled |

- **The residual** is a plain condition over the label set's attributes: subset checks for self and location, an overlap check for participants, and the seal clause. It maps directly onto array operators (e.g. Postgres subset and overlap).
- **The pipeline:**
  1. Compute the residual from the context.
  2. Run it as a query over the small label-set table.
  3. Pass the resulting IDs as the ID IN [...] pre-filter to the vector store.
- **Two partial-evaluation engines exist:**
  - The older one, used by cedarpy.
  - Typed partial evaluation (RFC 95). It produces well-typed residuals, but needs a schema and a context that is either fully known or fully unknown.
- **Filter compilation:** residuals convert to Cedar's public syntax tree. RFC 95 envisions translating them into SQL, but Cedar ships no translator, so we would write it.
- **A built-in resource query exists,** but it just checks every candidate after partial evaluation.
- **Published speed:** single checks take a median of 4–5 µs (p99 under 20 µs). That is 28.7–35.2× faster than OpenFGA and 42.8–80.8× faster than Rego, per the Cedar paper.

## Proving the high-assurance property

- **The analyzer:** cedar-policy-symcc compiles policies to SMT. The compiler is proven correct in Lean.
- **Checks available:** implies, equivalent, disjoint, always-allows and always-denies, each able to produce a counterexample.
- **How to state it:** write the property as its own policy, "read is permitted only if the current location covers every high-assurance label", and check that our policies imply it. That holds for every well-typed request and entity store. Comparing two versions of a policy set works the same way.
- **Caveats:**
  - It proves the property only relative to haLocs being computed correctly, which happens outside Cedar.
  - It needs the cvc5 solver.
  - It was not run here.

## Adding attributes and label types

- **New context attribute:** declare it optional in the schema and guard it with has; old policies stay valid.
- **New label type:** a new LabelSet attribute, empty by default, plus one clause per policy.
- **Entity tags** allow open-ended keys that share one value type.
- **Schema:** validation, typed partial evaluation and the analyzer all need it kept up to date.

## For benchmarking later

- **Existing benchmarks:** Cedar's own criterion benches, and the paper's setups (gdrive, github, TinyTodo; 100k random requests).
- **A fair complex-policy benchmark needs:**
  - the same semantics in every engine, checked against a brute-force oracle;
  - growing numbers of label sets, policies, environments and overlapping forbids;
  - separate timings for parsing, entity loading, evaluation and residual-to-filter compilation;
  - timings in the native core and in each binding;
  - separate timings for the one-time proof and for queries.
