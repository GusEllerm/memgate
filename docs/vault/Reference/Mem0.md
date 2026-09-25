---
type: reference
status: active
authority: reference
summary: "Mem0 (OSS v2.2.0 @ 8127e8b, 2026-09): now additive-only fact extraction over 26 vector stores, with metadata filters pushed into the store. No source lineage, add-time lookups ignore labels (scope-mixing leak), no faithful export. A 300–600 line fork on Qdrant or pgvector."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, mem0]
---

# Mem0

*Surveyed 2026-09-25 from the code at [mem0ai/mem0](https://github.com/mem0ai/mem0) commit 8127e8bd, plus docs ([platform vs OSS](https://docs.mem0.ai/platform/platform-vs-oss), [v2 to v3 migration](https://docs.mem0.ai/migration/oss-v2-to-v3)) and the [paper](https://arxiv.org/abs/2504.19413). Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** Mem0 has changed a lot since its 2025 paper. Consolidation is now add-only, and graph memory has been removed from the open-source version. Its filters are pushed into the vector store as real pre-filters, so our label check fits on Qdrant or pgvector.

But it keeps no source lineage. And its add-time lookup of existing memories ignores labels, so the LLM can copy content from other label sets into a new memory. Workable as a fork of about 300–600 lines. Avoid the hosted Platform.

## What it is

- Python SDK v2.2.0 and Node SDK v3.3.0, released 2026-09-23. Apache-2.0, very active.
- **Stack:** Python 3.10+, SQLite for history, Qdrant by default, optional spaCy.
- **Telemetry:** PostHog, on by default.
- **Stores:** 26 vector stores, including Qdrant, pgvector, Chroma, Milvus, Pinecone, Weaviate and Redis. The open-source version no longer has graph stores.
- **Hosted Platform:** adds app, org and project scopes, plus "Dream" (supersede, merge and synthesis) and optional memory decay.

## Memory model

- **Extraction.** One LLM call sees the new messages, the last 10 session messages and the top 10 existing memories. It returns only new facts, each attributed to user or assistant.
- **Add-only.** Exact duplicates are dropped by hash, and nothing is overwritten. Update and delete happen only when called explicitly.
- **Memory types:** an enum of semantic, episodic and procedural. Only procedural is acted on, and it is marked for removal.
- **"Graph memory"** is now a second collection of entities, each listing the memories linked to it. It boosts ranking only: there are no typed edges.

## Scoping and filters

- **Scope IDs:** open source scopes by user, agent and run IDs; search requires one of them.
- **Metadata filters:** any metadata key, with eq, ne, in, nin, contains, comparisons and AND/OR/NOT. They are translated into the store's native filter, so they run inside the search.
- **Support varies by store:**
  - Weaviate silently drops metadata filters.
  - Pinecone has no OR or NOT.
  - Wildcards do nothing on Qdrant and Chroma.
- **No access control** beyond these filters.

## Lineage and leaks

- **No source IDs.** Messages have no link to the memories extracted from them.
- **Partial history.** A history table records old and new text, the event and the actor. The LLM's links to related memories are discarded in the open-source version.
- **Scope-mixing leak.** At add time, both the lookup of existing memories and the entity upsert filter only on user, agent and run IDs. Label metadata is ignored, so the LLM sees memories from other label sets. It can copy their content into a new memory stamped only with the caller's labels.
- **Entity side channel.** Entities pool linked memories across all labels. Their boost weight counts memories the caller cannot read.
- **Recall.** Open-source search writes nothing to the store, but telemetry sends filter keys and hashed IDs. On the Platform, memory decay records a reinforcement on every recall.
- **Export.** None in open source beyond listing all memories. The Platform's export is an LLM job that fills a schema, not a faithful dump.

## Fit with our label model

| Requirement | Fit | Why |
| --- | --- | --- |
| Label pre-filter | Good, on Qdrant or pgvector | Nested AND/OR, or "in" over label-set IDs, is pushed into the store |
| Union inheritance | Needs a fork | Add-time lookup and entity upsert must take the label filter; union must be computed ourselves |
| Provenance | Needs a fork | Keep the related-memory links, give messages IDs, record sources |
| Entity store | Needs a fork | Entities must be label-aware, or kept per partition |
| High-assurance partitions | Good | Separate collections. Open source has no decay or usage counters; telemetry must be off |
| Export fidelity | Needs a fork | Write our own exporter for payloads and history |

**Effort:** about 300–600 lines in the core memory module, across both its sync and async paths.

## For benchmarking later

- **Vendor claims (current docs):** LoCoMo 92.5 and LongMemEval 94.4 at about 7k tokens per query.
- **Migration guide:** reports gains from v2 to v3.
- **The paper:** predates the current algorithm.
- The repo's evaluation folder is empty, so every number needs rerunning.
