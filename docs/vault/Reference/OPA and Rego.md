---
type: reference
status: active
authority: reference
summary: "OPA/Rego (v1.21.0, CNCF graduated, maintainers now at Apple): our rules are easy to write; a naive loop over label sets is linear (350 ms per query at 100k) but an offline inverted index gives 0.38 ms with identical output. Partial evaluation to SQL/UCAST doesn't fit multi-participant sets. No formal proofs, only bounded exhaustive tests. Also covers Casbin and Oso."
created: 2026-09-25
updated: 2026-09-25
tags: [memgate, reference, survey, policy-engine, opa]
---

# OPA and Rego

*Surveyed 2026-09-25. Experiments ran on OPA v1.21.0 (commit dc6269f). Sources: [releases](https://github.com/open-policy-agent/opa/releases), [changelog](https://raw.githubusercontent.com/open-policy-agent/opa/v1.21.0/CHANGELOG.md), [founders' note](https://www.openpolicyagent.org/blog/note-from-teemu-tim-and-torin-to-the-open-policy-agent-community-2dbbfe494371), docs on [filtering](https://www.openpolicyagent.org/docs/filtering), [partial evaluation](https://www.openpolicyagent.org/docs/filtering/partial-evaluation), [performance](https://www.openpolicyagent.org/docs/policy-performance), [integration](https://www.openpolicyagent.org/docs/integration) and [testing](https://www.openpolicyagent.org/docs/policy-testing), [regorus](https://github.com/microsoft/regorus), [Casbin ABAC](https://casbin.apache.org/docs/abac), [Casbin subset loading](https://casbin.apache.org/docs/policy-subset-loading) and [Oso list filtering](https://www.osohq.com/docs/develop/enforce/list-filtering). Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** A good, flexible engine, but it can't prove anything.
- **Writing the rules:** easy, and a new context attribute is one more rule.
- **Listing readable label sets:** a naive loop over label sets is linear, 350 ms per query at 100k. An inverted index built offline gives 0.38 ms with identical output, but the rules must then follow the index's layout.
- **Partial evaluation:** its SQL/UCAST output doesn't fit label sets with several participants.
- **Assurance:** no formal proofs, only bounded exhaustive tests. That compares poorly with [[Cedar]] for high-assurance locations.

## What it is

- **Version:** v1.21.0 (2026-09-24), Apache-2.0, released roughly monthly. CNCF graduated.
- **Governance:** OPA's creators and the Styra staff joined Apple on 2025-08-20. The project governance and licence are unchanged. EOPA is archived; its Compile API was merged into OPA in v1.9.
- **Embedding options:**
  - Go library.
  - REST sidecar.
  - Wasm (pure-Go wazero since v1.19).
  - IR plans (used by swift-opa).
  - REST SDKs for other languages.
- **No official Python SDK.** Microsoft's regorus is a Rust Rego interpreter with Python, JS and Java bindings (v0.12.0, compatible with OPA v1.2). It claims about 10x OPA's speed.

## Modelling our rules (tested)

```rego
granted contains sprintf("self:%s",[input.agent])
granted contains sprintf("loc:%s",[input.location])
granted contains sprintf("with:%s",[p]) if some p in input.participants
readable_ls(ls) if { every l in ls.self {l in granted}; every l in ls.loc {l in granted}; with_ok(ls) }
with_ok(ls) if count(ls.with)==0
with_ok(ls) if { some w in ls.with; w in granted }        # any one participant
default allow_derive := false                           # Severance write rule
allow_derive if { not env.severance; not high_assurance_violation; dropped_ok }
```

Environments are flags in data. A new context attribute only needs another granted rule.

**Note:** this sketch grants a participant label to every agent present. Our accepted rule grants with:X only to agent X itself ([[Label and Memory Types]]). The fix is one line, but the latencies above were measured with the sketch as written.

## Listing readable label sets

| Approach | 10k label sets | 100k label sets | Notes |
| --- | --- | --- | --- |
| Loop over every label set | 34 ms, 31 MB allocated | 350 ms, 309 MB allocated | Linear, too slow per query |
| Offline inverted index (by sorted self+loc labels, split into with and without participants) | 0.15 ms | 0.38 ms | Same IDs as the loop (checked). Rules must follow the index layout |

**Partial evaluation.**
- **Availability:** open source since v1.9, via the Compile API. It outputs SQL (Postgres, MySQL, SQL Server, SQLite) or UCAST.
- **Unsupported on unknowns:** "every", negation of a bare unknown, and defaults.
- **Blow-up:** the residual expands into OR-of-ANDs, 16 branches for one agent and two participants, growing multiplicatively.
- **Multi-participant sets** need an overlap test, which falls outside the supported expressions.
- **No vector-store output.**
- **Conclusion:** use the indexed enumeration over label-set IDs, not partial evaluation.

## Verification

- **Tooling:** unit tests with mocking and coverage, strict checking and the Regal linter. No formal semantics and no SMT checking.
- **High-assurance property:** it can only be checked as a **bounded exhaustive test**: for every agent and location in a small set, a high-assurance item must be unreadable outside its location.
- **The test caught a real leak.** A location hierarchy in which a child room grants its parent made a high-assurance vault readable from the lobby. See [[Label and Memory Types]].
- **Write rules** (*Severance*, the high-assurance label surviving derivation) are directly testable.

## Performance

- **Memory:** raw JSON data costs about 20x its size (10k ACL rules ≈ 130 MB; 100k ≈ 1.1 GB). The 18 MB index peaked at 332 MB RSS.
- **Rule indexing** covers equality, glob, membership and prefix matches.
- **Pitfalls:**
  - Loops over large data are linear in time and memory.
  - Stricter ":=" semantics since v1.19 can silently turn lookups into full scans.
  - Wasm and IR targets reject some recursion.

## Casbin and Oso

| Engine | For us | Why |
| --- | --- | --- |
| Casbin (Apache incubating) | Weak | ABAC matchers see only request fields, not stored policies. "Filtered policy" loads policy subsets, not our data. No residuals: one check per label set |
| Oso | Right shape, wrong deployment | list() returns authorised IDs, up to about 10k per user, which is exactly our ID IN [...] shape. list_local() returns SQL filters. But both need the managed Oso Cloud; the open-source Polar library has been deprecated since 2023-12 (search result only) |

## For benchmarking later

- **Candidates:** OPA as a Go library, via Wasm and via REST; regorus from Python; [[Cedar]]; and a hand-written bitset or index baseline.
- **Vary:** label sets from 10k to 1M, participants per context, depth of the location hierarchy, number of environments, and the share of label sets readable.
- **Measure:** p50/p99 latency, bytes allocated per query, RSS and reload time.
- **Keep** the high-assurance and *Severance* property tests as a regression suite that every engine must pass.
