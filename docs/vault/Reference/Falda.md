---
type: reference
status: active
authority: reference
summary: "Falda, evaluated as Rob Ross's fork (rbross-hpc/falda @ 0690078, 2026-09-05): four-tier SQLite memory with evidence links from atoms to source turns and physical per-store isolation. Tags exist but filter nothing; Core mixes a whole store; seven retrieval paths would need a label filter."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, falda]
---

# Falda

*Surveyed 2026-09-25. Evaluated as Rob Ross's fork, [rbross-hpc/falda](https://github.com/rbross-hpc/falda), at commit 0690078e (2026-09-05), per [[Decision Log]]. The fork was cloned and its tests run (607 pass, offline, about 12 s on Node 22). No paper exists. Facts are as of that date. Scored against [[Evaluation Criteria]]; listed in [[Architecture Survey]].*

**Verdict so far.** Falda is the only candidate with source lineage built in: every distilled atom links to the turns it came from. That makes "derived memory inherits its sources' labels" cheap to add for atoms. Its access model is the opposite of ours, though: coarse, physical isolation per store rather than labels filtered within a store. Its Core document is written from a whole store at once. Atoms already have a tags field, but nothing filters on it.

## What it is

"FALDA — clustered hierarchical memory for scientific agents" (*falda*: Italian for layer or stratum). Rick Stevens started it on 2026-06-22 under the name STRATUS. The AGENT-MEMORY README places it in a memory stack for long-lived agents at Argonne. There it is the "planned successor, currently shadow dual-run" to a system called TDAI, "hardened for 1,000-agent multi-tenant scale".

| Repo | State at survey | Notes |
| --- | --- | --- |
| [rbross-hpc/falda](https://github.com/rbross-hpc/falda) (Rob Ross's fork, **evaluated**) | 231 commits ahead of upstream, 0 behind; last commit 2026-09-05 | Everything in this note unless stated otherwise |
| [rick-stevens-ai/falda](https://github.com/rick-stevens-ai/falda) (upstream) | 26 commits, tip 2026-08-01, v0.1.0, Apache-2.0 | A two-tier schema (stream + atoms) with scenes as files. Its gateway trusts a tenant field in the request body (upstream PR #1). Upstream PR #3 back-ports only the fork's stats, reembed and embedder checks |

**Fork-only, not in upstream:**
- The four-tier SQLite model, evidence links, audit tables and header-based tenant auth.
- One server exposing HTTP and MCP, with a shared token file.
- Recall traces and a distillation queue with leases, a dead-letter queue and quarantine for content-filter failures.
- Operator CLIs: distill inspect, show recall, stats, reembed, backup and restore.
- A Python analysis TUI, a Dockerfile, Claude Code and opencode plugins, an Anthropic distillation provider and an in-process ONNX embedder.

The fork has Issues and Discussions disabled.

Companion repos: falda-demo, memory-falda (an OpenClaw plugin), ump-memory. Context: [rick-stevens-ai/AGENT-MEMORY](https://github.com/rick-stevens-ai/AGENT-MEMORY). The data model is adapted from shinzui/kioku.

## Architecture

TypeScript on Node. Storage is SQLite with sqlite-vec (vectors) and FTS5 (keywords). Embeddings come from any OpenAI-compatible endpoint or in-process ONNX. Distillation uses an OpenAI-compatible LLM (Ollama by default) or Anthropic.

| Tier | Holds |
| --- | --- |
| T0 Stream | Raw turns (session id, role; no labels) |
| T1 Atoms | Typed facts, patterns, preferences, constraints, instructions; priority, confidence, pinned, status, a tags JSON array |
| T2 Scenes | Episodes (one per session) and topics (embedding clusters), summarised by an LLM |
| T3 Core | One LLM-written core.md per store |

A background worker distills T0 → T1 → T2 → T3, deciding for each new atom whether to store, update, merge or skip.

**MCP tools.**
- Default: recall, remember, forget, distill, distill_status, whoami, stream_add.
- The "full" toolset adds direct query and search over stream, atoms and scenes, atom upsert and core read.

## Recall path and where a label filter would go

1. **Entry.** HTTP /recall (src/gateway.ts) or the MCP recall tool (src/mcp/tools/recall.ts).
2. **Identity.** A bearer token resolves to a principal with its tenants and pools. The tenant header and pool argument are checked against it (src/mcp_auth.ts). **This is where a label context would be built;** today the principal carries only tenant and pool lists.
3. **Store.** The pool manager resolves (tenant, pool) to exactly one store. There is no fan-out across stores.
4. **Assembly** (src/distill/context.ts), four steps that each need a filter:
   - Pinned atoms: added with no query at all.
   - Atom search: vector and keyword top-k (three times the limit), fused by reciprocal-rank fusion. Inactive rows are then dropped in JavaScript, so a filter placed there would lose recall. It belongs inside the vector and keyword queries.
   - Scene search: the same shape.
   - Core: added whenever more than 50 characters of budget remain.
5. **Render and trace** (src/recall/). Traces record item IDs, scores and the ranking policy snapshot.

**Other read paths that also need the filter:** stream search and query, atom query, scene endpoints, core read, recall reconstruction, and the full MCP toolset. Recall itself never searches raw turns.

**Tags today.**
- Written by remember and atom upsert.
- Read into the atom object.
- Never used in any filter.
- Distilled atoms get no tags.
- An update-tags method exists but has no callers.

## Scoping and access control

- **Stores.** Isolation is physical: one SQLite file per store, a private store per tenant plus shared pools. The design deliberately rejects filtering rows within a store.
- **Pools.** Members get none, read or readwrite access.
- **Lineage.**
  - An atom-evidence table links each atom to its source turns.
  - Evidence is combined **only inside the distillation apply loop**. A manual merge or supersede over HTTP just changes status and does not combine evidence.
  - Deleting a turn removes its rows, index entries and evidence links in one transaction, and returns the affected atom IDs. The atoms themselves are kept.
- **Audit.** Every distillation decision is recorded. Pool writes are not audited.
- **Pool distillation.** The periodic sweep covers only private stores, but an explicit distill call on a pool does run. Inferred from the code but not tested: the distillation watermark is keyed by tenant and pool, so two members distilling the same pool could extract the same turns twice.
- **Deferred in the fork's docs:** multi-store search, a pool audit log, and attributing pool turns to the tenant that wrote them.

## Core (T3)

- **Built by:** an LLM, from every active scene and its atoms, in one pass per store. It is regenerated only when its input hash changes, and deleted when there are no scenes.
- **Read by:** recall assembly, the core read endpoint and the core read MCP tool.
- **No way to withhold it.** The only control is Core's share of the token budget, and the HTTP and MCP entry points always use the defaults.

## Fit with our label model

| Requirement | Fit | Why |
| --- | --- | --- |
| Label-filtered retrieval | Moderate effort | Seven read paths plus pinned atoms need the filter. It must go inside the vector and keyword queries, not into the JavaScript pass after the top-k cut |
| Labels on raw turns | Missing | Stream rows carry only session and role |
| Derived atoms inherit labels | Feasible | Evidence links make an atom's labels computable from its source turns. Manual merges must be fixed to combine evidence first |
| Derived summaries inherit labels | Breaks | Scenes and Core are written from everything in a store, so they mix all labels. They would need synthesis per label set, or exclusion |
| Coarse isolation today | Available | Tenant and pool stores can stand in for coarse labels, but only one store is searched per call |
| Side channels | At risk | Keyword (FTS5) ranking statistics are shared across the whole store; see [[Vector Store Label Filtering]] |

## For benchmarking later

- **Running it:** needs a token file and an embedder (ONNX, about a 440 MB download, or an OpenAI-compatible endpoint such as Ollama). Distillation needs an LLM. Docker is optional.
- **Tests:** deterministic and offline with the local hash embedder. CI covers Node 20–26 on Linux and macOS.
- **Traces:** recall traces record per-item tier, score and usage (used or unused), and metrics endpoints aggregate them. A distillation pass can be exported as a replay fixture.
- **No eval set:** MODEL.md describes a retrieval evaluation set, but none exists in the repo. No public benchmark results were found.
- **Fairness:** hold the distillation LLM fixed.

## Open

- Gus's brief places Falda at UChicago; the repos mention only Argonne. Rick Stevens holds posts at both, so this is probably the same thing.
