---
type: reference
status: active
authority: reference
summary: "Graphiti (graphiti-core 0.30.2 @ 47f6482), Zep's open-source temporal knowledge graph: one partition key (group_id), no per-item permissions, graph walks that check only their end nodes, and entity and community summaries that mix every source. Label model needs a deep fork."
created: 2026-09-25
updated: 2026-09-25
tags: [memgate, reference, survey, knowledge-graph]
---

# Zep and Graphiti

*Surveyed 2026-09-25 from the code at [getzep/graphiti](https://github.com/getzep/graphiti) commit 47f64821, and from docs on [searching](https://help.getzep.com/graphiti/working-with-data/searching), [namespacing](https://help.getzep.com/graphiti/core-concepts/graph-namespacing), the [open-source strategy post](https://blog.getzep.com/announcing-a-new-direction-for-zeps-open-source-strategy/) and the [Zep paper](https://arxiv.org/abs/2501.13956). Facts are as of that date. Listed in [[Architecture Survey]].*

**Verdict so far.** The knowledge-graph family's main problem shows up here. An entity like "Project X" is one node shared by memories from every location, and its summary mixes all their facts. Graphiti has one partition key and no per-item permissions. Graph walks check only their end nodes. A label model would need a deep fork, several weeks of work, against a fast-moving 0.x codebase. High-assurance partitions fit well.

## What it is

- **Graphiti** (graphiti-core 0.30.2) is the maintained open-source part: Apache-2.0, about 31k stars, still 0.x with APIs that change often.
- **Stack:** Python, async. LLM clients for OpenAI, Anthropic, Gemini and Azure. There is an MCP server.
- **Graph backends:** Neo4j, FalkorDB and Neptune (with OpenSearch for full text). Kuzu is deprecated.
- **Zep Community Edition** ended on 2025-04-02 and now sits in a legacy folder. **Zep Cloud** is proprietary and paid.

## Architecture

- **Episodes.** A message, text or JSON record is an episode. It links to the entities it names.
- **Extraction.** An LLM extracts entities and resolves duplicates by embedding search plus LLM judgement. It then extracts facts (edges) and dedupes them.
- **Two time axes.** Edges carry both event time (valid/invalid) and system time (created/expired). Contradicted facts are expired, not deleted.
- **Summaries.** Communities are built by label propagation, and their summaries by pairwise LLM summarisation. Rolling "saga" summaries cover runs of episodes.
- **Search.** BM25, cosine similarity and graph traversal, reranked by RRF, MMR, node distance, episode mentions or a cross-encoder. Search writes nothing.

## Scoping

- **group_id** is on every node and edge, and is filtered inside every query. The docs say it "does not replace application authorization".
- **Other filters:** node labels, edge types and time ranges.
  - Node-label matching means "any" on Neo4j and FalkorDB but "all" on Kuzu.
  - A property-filter option is declared but never used.
- **Where the filter runs:**
  - **Vector search** is a brute-force scan that filters first: a true pre-filter, with no ANN index.
  - **Full-text search** takes the index's top hits and then filters. Nothing leaks, but recall drops under tight filters.
  - **Graph traversal** filters only the end nodes of a path, not the hops in between. A walk can pass through facts a context shouldn't see and return what lies beyond them.

## Lineage

- **Facts** list their source episodes, and duplicates append new episodes.
- **Entity nodes** have no provenance field; their sources are reachable only through episode links.
- **Dedup** stays within a group_id. Within a group, entities from different episodes merge silently.
- **Summaries.** An entity's summary is rewritten from every new episode and fact, and a community's summary mixes all its members' summaries. Neither records its sources.
- **Removing an episode** deletes a fact only if that episode was its first source.

## The shared-node problem

| Option | How | Cost |
| --- | --- | --- |
| A. Label facts, filter traversal | Label every edge and check every hop | Entity summaries, community summaries and embeddings still mix labels. They must be dropped, or kept per label set at multiplied LLM cost |
| B. Duplicate nodes per label set | Encode a label-set ID into group_id | Strong isolation for free, since dedup, communities and walks stay in one group. But "Project X" splits into unlinked nodes, cross-location provenance needs an extra layer, and "any one participant" means querying many groups |

## Fit with our label model

**Needed:**
- Label-set IDs on every node and edge.
- Replacing group_id filtering in about 20 queries per backend, across four backends.
- Filtering every hop of a graph walk.
- Label-aware dedup, or union labels on merge.
- Per-label-set or union-labelled summaries, communities and sagas.
- Label-aware episode removal.

**Fits already:**
- **High-assurance partitions:** a separate group_id or database, and search never writes.
- **Export:** there's no tool, so it would be a Cypher dump; labels survive only if stored as properties.

## For benchmarking later

- **Zep paper (vendor claims):** 94.8% on DMR versus MemGPT's 93.4%, and on LongMemEval up to 18.5% better accuracy with 90% lower latency.
- **Vector search** is brute force with no ANN index, so it will scale differently from the vector stores.
