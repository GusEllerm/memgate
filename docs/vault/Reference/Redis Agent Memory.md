---
type: reference
status: active
authority: reference
summary: "Redis Agent Memory (part of Redis Iris, managed, preview since 2026-05) and its open-source predecessor agent-memory-server V0. The managed product is closed and scopes by store plus a caller-supplied owner id; V0 already pre-filters tag sets inside the KNN query and is a good base for our label model, but is no longer the supported line."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey, redis]
---

# Redis Agent Memory

*Surveyed 2026-09-25. Facts are as of that date. Scored against [[Evaluation Criteria]]; listed in [[Architecture Survey]].*

**Verdict so far.** Two different things share the name. The managed product is a poor fit: it is closed, its boundary is a whole store plus an owner id the caller supplies, and its extraction reads mixed inputs. The open-source V0 server is a good base: its tag filters already run inside the vector query, with any-of and all-of set operators. What it lacks is enforcement (the caller's claims never scope data) and label inheritance for derived memories.

## What it is

| Version | Status | License | Links |
| --- | --- | --- | --- |
| Redis Agent Memory (in Redis Iris) | Managed on Redis Cloud, preview; announced 2026-05-18; self-managed Redis Software in private preview | Proprietary | [product](https://redis.io/agent-memory/), [docs](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/), [developer guide](https://redis.io/docs/latest/develop/ai/context-engine/agent-memory/developer-guide), [announcement coverage](https://siliconangle.com/2026/05/18/redis-debuts-much-needed-memory-layer-enterprise-ai-agents/) |
| agent-memory-server V0 | Moved to a V0 folder, "kept as an open research artifact, not as the supported production distribution"; last server release v0.15.2 (2026-04-10) | Apache-2.0 | [repo](https://github.com/redis/agent-memory-server), [releases](https://github.com/redis/agent-memory-server/releases) |

Iris is Redis's "context engine": Agent Memory, Context Retriever, Data Integration, LangCache and Search. LangCache (semantic cache) and Context Retriever (a semantic model over business data, served over MCP) are not memory stores.

## Architecture

- **Two tiers.** Session memory: ordered events (event, session and actor ids, role, content, metadata) with a TTL. Long-term memory: text plus embeddings, own TTL.
- **Background processing.** Older session events are summarised past a threshold; facts are extracted into long-term memory on a set cadence. Custom memory types carry their own extraction prompt and typed fields.
- **Sensitive-data exclusions.** Regex and built-in detectors that redact or drop, plus an advisory semantic prompt. They apply only to automatic extraction, and the docs warn sensitive content "still reaches the extraction model provider".
- **Search.** Semantic, keyword or hybrid.
- **Interfaces.** Managed: Python and TypeScript SDKs, REST, MCP, OAuth2/JWT. V0: Python/FastAPI with an MCP server, RedisVL indexes on the Redis Query Engine, BERTopic for topics.

## Scoping and access control

| | Managed product | V0 server |
| --- | --- | --- |
| Boundary | One API key per store; store id in the request path | JWT or token auth, but the authenticated user is only a gate: user id and namespace come from the caller and are trusted |
| Scope fields | Owner id, session id, namespace, topics, memory type | User id, session id, namespace, topics, entities |
| Filter semantics | "Use ownerId to restrict recall": a caller-passed filter, not an access rule. Operators and pre- vs post-filtering unconfirmed (API reference rendered empty) | Tag filters with eq, ne, any, all, not_in, startswith, ANDed and passed into the KNN, range and hybrid queries: pre-filtered |
| Lineage | No provenance field documented | Each memory has an extracted-from list of message ids. Summaries take them from the thread; discrete facts take whatever the LLM returns. One level deep, best-effort. LLM merging drops it: the merged record has no extracted-from list, takes the first non-empty namespace and session, and unions topics, so consolidation can mix namespaces (it does refuse to merge across user ids) |
| Label inheritance | None | None; session and context summaries carry no labels |

## Fit with our label model

Managed product: would need a separate store per label set, or our own gateway in front. We could not guarantee extraction and summarisation read only unlocked sources.

V0 fork, moderate effort:

1. Add a labels tag field. Inject the filter server-side from the unlocked set. For "all of an item's labels must be allowed", the filter is "no label from the locked set" (not_in over every label outside the allowed set), which needs the full label universe. "Any of the allowed labels" is not equivalent: it admits an item tagged with one allowed and one locked label.
2. Bind the context to JWT claims, not request parameters.
3. Make derived labels the union of source labels at extraction and summarisation. That needs deterministic source ids, not LLM-supplied ones, and labels on working-memory messages and context summaries.
4. Filter working-memory reads too.

Main risk: V0 is no longer the supported product line.

## For benchmarking later

Benchmark V0 (self-hostable) with the label field and server-side filter added; the managed preview can only be benched as a black box behind a gateway. Hold the extraction LLM fixed.
