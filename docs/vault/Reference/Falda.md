---
type: reference
status: active
authority: reference
summary: "FALDA, Rick Stevens' self-hosted tiered memory engine for scientific agents: strong provenance from atoms to source turns, isolation by physical store per tenant/pool, no per-item filtering at retrieval yet."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, falda]
---

# Falda

*Surveyed 2026-09-25 from the GitHub repos and their docs (POOLS.md, MODEL.md, source). There is no paper yet. Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** Falda's provenance is the best fit for "derived memories inherit source labels". Its permission model is coarse: one physical store per tenant or pool. Per-item label filtering would have to be added to every search path, and the T3 Core summary is the hard case.

## What it is

- **FALDA**, a self-hosted memory engine for scientific agents. Rick Stevens made the first commit on 2026-06-22, under its earlier name STRATUS: "clustered hierarchical memory for scientific agents".
- **Canonical repo:** [rick-stevens-ai/falda](https://github.com/rick-stevens-ai/falda).
  - Apache-2.0, version 0.1.0, no releases.
  - 26 commits, last push 2026-08-15.
- **Most active fork:** [rbross-hpc/falda](https://github.com/rbross-hpc/falda), by Rob Ross.
  - 257 commits, last on 2026-09-05.
  - Adds an MCP surface, recall traces, failure handling, an analysis TUI and a Docker image.
- **Related repos under the same account:**
  - AGENT-MEMORY: a white paper plus the TDAI/STRATUS/UMP specs.
  - falda-demo: tenant isolation and shared pools.
  - memory-falda: an OpenClaw plugin.
  - ump-memory: a "Universal Memory Protocol" reference.
- **Stack:** TypeScript, SQLite with sqlite-vec and FTS5, any OpenAI-compatible embedder, and an optional Anthropic model for distillation.
- **Integrations:** Claude Code, opencode, OpenClaw and Hermes.

## Architecture

Four tiers (family: tiered, with an episodic/semantic split):

| Tier | Holds |
| --- | --- |
| T0 Stream | Raw conversation turns |
| T1 Atoms | Typed facts, patterns, preferences, constraints, instructions |
| T2 Scenes | Episodes grouped by session, and topics built by clustering embeddings |
| T3 Core | One persona/project document per store |

**Writing and consolidation.**
1. Agents write turns to the Stream.
2. A background worker extracts atoms from windows of turns.
3. An LLM consolidates each candidate against existing atoms: store, update, merge or skip.
4. Scenes are built next, then Core is synthesized.

**Retrieval.**
- Hybrid dense and BM25 search, fused by reciprocal-rank fusion.
- Re-ranked on recency, priority and confidence, with a pinned-first pass.
- Context assembly packs all tiers into a character budget.
- Exposed over HTTP and MCP (recall, remember, forget, distill).

## Scoping and access control

- **Partitioning:** memory is split by tenant and pool. The tenant comes from a request header plus a bearer token.
- **One SQLite file per store:** each tenant's private "self" store and each shared pool is its own file. The docs reject a shared tenant column filtered in queries as prone to leaks.
- **Pools:** declared explicitly, with per-member access of none, read or readwrite.
- **Retrieval scope:** each search hits exactly one store. There are no session or agent-role filters at retrieval; session_id is only recorded on turns.
- **Provenance:**
  - An evidence table links each atom to its source turns, at the granularity of the extraction window.
  - Merges and updates keep the union of all sources.
  - Every distillation decision is logged.
  - Deleting a turn reports the atoms that depended on it, but does not delete them.
- **Stated gaps:** shared pools are not distilled, and pool writes have no audit log.

## Fit with our label model

- **Label filtering at retrieval (moderate work).**
  - Atoms already have a JSON tags column, documented as filter-only.
  - But the atom, scene and stream search functions take only a query and a limit.
  - We would have to push the label filter into the vector and full-text queries and into context assembly, and add labels to the Stream and Scene tables.
- **Label inheritance (feasible, not built).**
  - Atoms: the union of their source turns' labels, taken from the evidence table.
  - Scenes: the union of their atoms' labels.
  - Embeddings: one per row, so no mixed content.
- **Core is the blocker.** It compresses the whole store into one document. It would need to be built per label set, or withheld whenever any of its sources is locked.
- **Risk:** LLM consolidation merges atoms across sources, which mixes labels. Union inheritance keeps this safe but makes merged atoms harder to unlock.
- **Natural fit today:** one store per label set, which gives coarse labels rather than fine per-item labels.

## For benchmarking later

- Self-hosted SQLite, so it is easy to run locally.
- Recall traces and a retrieval-policy snapshot exist for evaluation. No public LoCoMo or LongMemEval results were found.
- Distillation needs an LLM, so benchmarks should separate write-path cost from recall latency.
