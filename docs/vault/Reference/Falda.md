---
type: reference
status: active
authority: reference
summary: "Falda: tiered, clustered memory for science agents from Rick Stevens' group (Argonne). Isolation is physical (one SQLite store per tenant or pool); atoms keep evidence links to source turns, so label inheritance is feasible, but LLM-written scenes and core mix everything in a store."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, falda]
---

# Falda

*Surveyed 2026-09-25 from the repos below; no paper exists. Facts are as of that date. Scored against [[Evaluation Criteria]]; listed in [[Architecture Survey]].*

**Implementation under evaluation: Rob Ross's fork, [rbross-hpc/falda](https://github.com/rbross-hpc/falda)** ([[Decision Log]], 2026-09-25). A deeper pass on the fork, pinned to a commit, is in progress.

**Verdict so far.** Falda is the only candidate yet with source lineage built in: every distilled fact links to the turns it came from. That makes "derived memory inherits its sources' labels" cheap to add for facts. Its access model is the opposite of ours, though: coarse, physical isolation per store rather than labels filtered within a store, and its highest-level summaries are written from a whole store at once.

## What it is

"FALDA — clustered hierarchical memory for scientific agents" (*falda*: Italian for layer or stratum). Started by Rick Stevens on 2026-06-22 under the name STRATUS. The AGENT-MEMORY README places it in a memory stack for long-lived agents at Argonne, as the "planned successor, currently shadow dual-run" to a system called TDAI, "hardened for 1,000-agent multi-tenant scale".

| Repo | Commits | Last push | Notes |
| --- | --- | --- | --- |
| [rick-stevens-ai/falda](https://github.com/rick-stevens-ai/falda) (upstream) | 26 | 2026-08-15 | 4 stars, 5 forks, v0.1.0, no releases, Apache-2.0 |
| [rbross-hpc/falda](https://github.com/rbross-hpc/falda) (Rob Ross's fork) | 257 | 2026-09-05 | Far more active: MCP docs, data-model doc, failure handling, Python analysis TUI, ~50 test files |

Companion repos: falda-demo, memory-falda (an OpenClaw plugin), ump-memory. Context: [rick-stevens-ai/AGENT-MEMORY](https://github.com/rick-stevens-ai/AGENT-MEMORY). The data model is adapted from shinzui/kioku.

## Architecture

TypeScript on Node, ~11k lines. Storage is SQLite with sqlite-vec (vectors) and FTS5 (keywords). Embeddings from any OpenAI-compatible endpoint or in-process ONNX; distillation by an OpenAI-compatible LLM or Anthropic. Served over HTTP and MCP.

| Tier | Holds |
| --- | --- |
| T0 Stream | Raw turns (session id, role; no labels) |
| T1 Atoms | Typed facts, patterns, preferences, constraints, instructions; priority, confidence, pinned, status, a tags JSON array |
| T2 Scenes | Episodes (one per session) and topics (embedding clusters), summarised by an LLM |
| T3 Core | One LLM-written core document per store |

A background worker distills T0 → T1 → T2 → T3, deciding per new atom whether to store, update, merge or skip. Recall fuses vector and keyword hits (reciprocal-rank fusion), re-ranks by recency, priority and confidence, puts pinned atoms first, and fills a token budget across tiers.

## Scoping and access control

- Every call names a (tenant, pool) pair; bearer-token auth, tenant in a request header.
- Isolation is physical: one SQLite file per store (a private store per tenant, plus shared pools). The design deliberately rejects row filtering.
- Shared pools declare members with none, read or readwrite access.
- Recall searches exactly one store; searching several at once is deferred.
- Lineage: an atom-evidence table links each atom to its source turns; merges and updates combine evidence and never drop it. An audit table records consolidation decisions.
- Deferred upstream: distilling shared pools, per-tenant attribution of pool writes, a pool write audit log, erasure.

## Fit with our label model

| Requirement | Fit | Why |
| --- | --- | --- |
| Label-filtered retrieval | Moderate effort | Search runs over the whole table, then drops inactive rows in JavaScript. A label check fits there, but filtering after the row limit loses recall; a proper fix needs pre-filtering or larger candidate pools. |
| Labels on raw turns | Missing | Stream rows carry only session and role. |
| Derived facts inherit labels | Feasible | Evidence links make an atom's labels computable from its source turns; merges already carry evidence forward. |
| Derived summaries inherit labels | Breaks | Scenes and Core are written from everything in a store, so they mix all labels. They would need per-label synthesis or exclusion. |
| Coarse isolation today | Available | Tenant and pool stores can stand in for coarse labels, but only one store is searched per call. |

## For benchmarking later

No published benchmarks. The docs describe a retrieval evaluation set and recall traces for tuning, and call the ranking weights provisional. A fair benchmark needs the distillation worker's LLM held fixed, and must bench the fork, not just upstream.

## Open

- Gus's brief places Falda at UChicago; the repos only mention Argonne. Rick Stevens holds posts at both, so this is probably the same thing.
- ~~Which repo is canonical: upstream or Rob Ross's fork?~~ Gus: evaluate Rob Ross's fork (2026-09-25).
