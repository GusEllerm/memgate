---
type: reference
status: active
authority: reference
summary: "Redis Agent Memory (managed, closed, part of Redis Iris, preview) and its open-source predecessor Agent Memory Server V0: V0 has real set-semantics tag pre-filters inside the vector query and a lineage field, but merging drops lineage and access is not enforced."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, redis]
---

# Redis Agent Memory

*Surveyed 2026-09-25 from Redis docs, the announcement coverage, and the Agent Memory Server repo and code. Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** The managed product (Iris) is a poor fit: extraction runs on Redis's servers, and one API key covers a whole store. The open-source V0 has the building blocks we need, so a fork is plausible. Its tag filters with "all" and "not in" semantics run inside the vector query, and records carry a lineage field. The work is enforcement and fixing lineage through merges.

## Two systems

| | Redis Agent Memory (Iris) | Agent Memory Server V0 |
| --- | --- | --- |
| What | Managed memory service in Redis Iris, Redis's "context engine" for agents | The earlier open-source server, now kept as a "research foundation" |
| Status | Public preview on Redis Cloud; private preview on Redis Software. Iris announced 2026-05-18 ([SiliconANGLE](https://siliconangle.com/2026/05/18/redis-debuts-much-needed-memory-layer-enterprise-ai-agents/)) | Last server release v0.15.2 (2026-04-10); code moved into a V0 folder, effectively frozen |
| Source | Closed; Python and npm SDKs plus REST | [redis/agent-memory-server](https://github.com/redis/agent-memory-server), Apache-2.0, Python/FastAPI, REST and MCP |
| Docs | [Product page](https://redis.io/agent-memory/), [docs](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/), [developer guide](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/developer-guide) | Repo README and code |

LangCache, another Iris component, is a semantic cache, not a memory system.

## Architecture

- **Iris:**
  - Session memory holds ordered events (session, actor, role, content, metadata) with a TTL.
  - Older events are summarised automatically, while recent ones stay in full.
  - Long-term memories are extracted in the background on a configurable schedule.
  - Custom memory types each get their own extraction prompt and typed fields.
  - Search is semantic, keyword or hybrid.
  - Sensitive-data exclusion uses regex detectors plus an "advisory" semantic prompt; sensitive content still reaches the model provider.
- **V0:**
  - Working memory is promoted to long-term memory.
  - An LLM deduplicates and merges memories.
  - Storage is the Redis Query Engine through RedisVL, using vector, range and hybrid queries.

## Scoping and access control

- **Iris:**
  - A store is reached with an endpoint, a store ID and one bearer API key.
  - No per-owner or per-agent authorisation is documented.
  - Search can filter on owner, session, namespace, topics and memory type.
  - How filters are applied internally is not documented, and the API reference page did not render, so the operators are unconfirmed.
- **V0:**
  - Tag filters support eq, ne, any, all, not_in and startswith on fields such as topics, entities, namespace and user_id. "All" and "not in" give us subset checks.
  - Filters are passed into the RedisVL query, so they are **pre-filters inside the KNN search**, not post-filters.
  - OAuth2/JWT authentication exists, but the API never reads the authenticated user. The user_id is whatever the caller sends, so the caller's identity is checked but not what it may see.

## Lineage

- **V0:** each memory record has an extracted_from field listing its source message IDs. The thread-aware extraction path fills it in.
  - **LLM merging drops it.** The merged record has no extracted_from.
  - Merging refuses to cross user IDs. Otherwise it takes the first non-empty namespace and session and unions the topics.
  - So consolidation can mix namespaces and loses lineage.
- **Iris:** long-term memories document no provenance field. Session summaries only carry a pointer to the last event they cover.

## Fit with our label model

- **Iris (hard).**
  - Labels could live in topics or namespace.
  - But derived memories are made server-side, so we can't make them inherit labels or stop them mixing across labels.
  - With one key per store, there is no authorisation per context.
  - The realistic option is one store or namespace per label combination, behind our own gateway.
- **V0 fork (moderate).**
  - Add a labels tag field and inject an all / not_in pre-filter from the context in the API and MCP layer.
  - Take identity from the JWT rather than from the caller.
  - Set derived labels to the union of source labels during extraction, merging (fixing its lineage drop) and summarisation.
  - Block merges across different label sets.
  - Label working memory per message rather than per session.

## For benchmarking later

- V0 is self-hostable against Redis Stack.
- The repo root now holds a LongMemEval benchmark harness, which could be reused for recall quality.
- Iris is preview-only on Redis Cloud, so benchmarks against it would include network latency and preview terms.
