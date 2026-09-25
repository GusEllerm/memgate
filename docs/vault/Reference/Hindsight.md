---
type: reference
status: active
authority: reference
summary: "Hindsight (v0.10.1 @ 415a8d7, MIT): Postgres/pgvector memory with facts → observations → mental models. Tag filters run inside SQL for three of four search arms, observations record their source facts, and a validator extension can overwrite a request's tags, so label-set IDs plus Cedar fit with no core changes. Opinions were removed in 2026."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, hindsight]
---

# Hindsight

*Surveyed 2026-09-25 from [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) commit 415a8d76 (v0.10.1), its local docs, the [paper](https://arxiv.org/abs/2512.12818) and the [benchmarks site](https://benchmarks.hindsight.vectorize.io/). Facts are as of that date. Listed in [[Architecture Survey]] and [[Memory System Landscape]].*

**Verdict so far.** The best fit among the self-hostable systems, and the cheapest to adapt.
- **The mapping:** give each item exactly one tag, its label-set ID. Cedar's partial evaluation gives the allowed IDs. A validator extension injects them into every recall as "any of these tags", which becomes an overlap check inside the HNSW query: our pre-filter, with no core changes.
- **Lineage:** observations record their source facts.
- **Clean recall:** recall writes nothing.
- **Gaps:**
  - The graph search arm filters after retrieval.
  - Reflect's tag scope can't be forced by the validator.
  - A table logging LLM requests is on by default.
  - Some consolidation modes deliberately widen scope.
  - The opinion network the paper describes no longer exists.

## What it is

- **Version:** v0.10.1 (2026-09-21), MIT. About 29k stars, created 2025-10.
- **Pace:** very fast: more than 100 migrations, and a 23k-line core engine file.
- **Stack:**
  - Python/FastAPI.
  - PostgreSQL with pgvector (HNSW with iterative scan, one index per bank) plus BM25. Oracle 23ai is an alternative, and an embedded Postgres is available for local use.
  - 25+ LLM providers, including local ones.
  - Clients in Python, TypeScript, Go and a CLI, and an MCP endpoint per bank.
- **Self-hosting:** Docker, pip, Helm or embedded.

## Architecture

- **Retain:** one LLM call per chunk extracts facts with what, when, where, who and why fields, typed as world or experience. Entities are resolved, and temporal, semantic, entity and causal links are stored.
- **Observations:** a background consolidation job after each change.
  - Facts are batched by tag scope.
  - Recall finds related observations, then one LLM call decides to create, update or delete.
  - Observations keep a proof count and a history.
  - Automatic consolidation can be switched off and run manually.
- **Mental models:** stored questions whose answers reflect writes and refreshes.
- **Recall:** semantic, BM25, graph and temporal search, merged by reciprocal-rank fusion and reranked by a cross-encoder. No LLM is involved.
- **Reflect:** an agent loop over mental models, observations and facts.
- **Opinions were removed.** A 2026-01 migration deleted them, and a 2026-04 migration dropped the confidence score. The paper's four networks and its confidence updates are history.

## Scoping

- **Banks:** rows keyed by bank ID in shared tables. A tenant extension can give each tenant its own Postgres schema, with a built-in API-key implementation. There is no per-user authentication inside a tenant.
- **Tags:** match modes any, all, any_strict, all_strict and exact, plus nested AND/OR/NOT groups.
- **Where the tag filter runs:** inside SQL for the semantic, BM25 and temporal arms. The graph arm filters in Python after scoring.
- **The key hook:** a validator extension can overwrite a recall request's tags and tag groups before search. For reflect it can only accept or reject.
- **Direction:** tag semantics test "the item has the request's tags", not "the reader holds every label on the item". With exactly one label-set ID per item, the two coincide.

## Lineage

- **Observations** store their source memory IDs. Mental models store what they were based on, and a retraction module handles cited facts that no longer exist.
- **Facts** link to their document and chunk. There is no agent-to-agent provenance.
- **Consolidation scope:**
  - Related observations are matched with all_strict on the fact's tags, so an observation's tags always include its facts' tags, and updates union them.
  - But the per_tag, all_combinations, explicit-list and "shared" scope modes deliberately let a fact feed a wider or untagged scope, with only a prompt asking the LLM to redact.
  - Untagged facts can fold into any tagged observation.

## Fit with our model

| Requirement | Fit | How |
| --- | --- | --- |
| Label pre-filter | Good | One tag per item = label-set ID; the validator injects the allowed IDs as any_strict, applied inside the HNSW query |
| Graph search arm | Gap | Filters after scoring: disable it or patch it |
| Union inheritance | Good, with settings | Default "combined" scope keeps consolidation within one label-set ID; the environment must forbid the widening scope modes; a retain validator can rewrite what is stored |
| Relaxation | Maps | An explicit observation-scope target plus a mission prompt, with the environment's approval |
| Personal memory | Rebuild | Opinions are gone; use observations or mental models tagged self:A. Writing an observation is automatic, not a separately gated step |
| Recall side effects | Good, with settings | Recall writes no memory. The audit log (off by default) and the LLM-request log (**on by default**) must be off in high-assurance partitions |
| High-assurance partitions | Good | A tenant schema per location |
| Export fidelity | Good | A ZIP of documents, facts with tags and metadata, causal links and optionally observations with their sources |
| Cross-agent provenance | Missing | Must be added |

**Effort:** small to medium. Label-set IDs as tags, a validator that calls Cedar, and a tenant schema per high-assurance location need no core changes. The risk is a fast-moving fork base.

## For benchmarking later

- **Paper:** LongMemEval 91.4%, LoCoMo 89.61%.
- **Benchmarks site** (no model or date given): LongMemEval-S 94.6%, LoCoMo10 92%, PersonaMem32K 86.6%, BEAM 64–75%.
- **Reproduction:** the README says external groups reproduced the results; not verified.
