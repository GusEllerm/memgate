---
type: reference
status: active
authority: reference
summary: "Two layers surveyed separately: memory stores (label-filtered retrieval, derived-data lineage) and policy engines (context attributes to allowed labels). None surveyed yet."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey]
---

# Architecture Survey

*As of 2026-09-25 no candidate has been surveyed. Each gets its own `Reference/` note when it is, linked from its row. Scored with [[Evaluation Criteria]].*

## Findings so far (2026-09-25)

- **Filtering search by label is the easy part.** Most systems can, or can be made to, filter inside the search: Redis V0, Mem0 on Qdrant or pgvector, and any vector store using label-set IDs.
- **Where memories get combined is the hard part.** Every system mixes labels or loses sources wherever memories are combined:
  - Mem0's add-time lookup ignores labels.
  - Redis V0's merge drops lineage.
  - Graphiti's entity summaries and Letta's rewritten core files mix every source.
  - Collaborative Memory lets an LLM strip content before sharing it.
  - Falda alone keeps source links through its condensing step. But its scenes and Core still mix a whole store.
- **Store-wide summaries are incompatible with selective memory** unless there is one per label set. This covers Falda's Core, Graphiti's communities, Letta's core files and Redis's session summaries.
- **Cheapest forks:** Mem0 (300–600 lines) and Redis V0. Falda has the best lineage, but seven read paths need filters. Graph systems are the deepest work.

The permission layer is surveyed separately from the memory store ([[Decision Log]], 2026-09-25). A store is judged on whether it can filter retrieval by label and track which items derived memories came from; a policy engine is judged on turning an open-ended set of context attributes into allowed labels. A store with built-in permissions gets no extra credit.

## Memory stores

| Architecture | Where memory lives | Permission question to answer | Status |
| --- | --- | --- | --- |
| Vector store RAG | Embeddings + metadata | Can metadata filters enforce locks at query time without leaking via similarity? | surveyed: yes if filtered inside the search; subset check native only in pgvector and Qdrant, label-set IDs work everywhere. See [[Vector Store Label Filtering]] |
| Knowledge graph | Nodes and edges | Can locks apply per node/edge, and do traversals respect them? | not surveyed |
| Tiered / OS-style (core, recall, archival) | Paged in and out of context | Does paging map cleanly onto unlock and lock events? | not surveyed |
| Episodic + semantic split | Raw episodes plus distilled facts | Do distilled facts inherit the locks of their source episodes? | not surveyed |
| File / document based | Files the agent reads and writes | Can filesystem-style ACLs serve as the permission layer? | not surveyed |
| Hybrid | Several of the above | Is one policy engine enforceable across all stores? | not surveyed |

## Named systems

Specific systems, mapped to the families above.

| System | Family | Question to answer | Status |
| --- | --- | --- | --- |
| [[Falda]] (Rob Ross's fork, rbross-hpc/falda) | Tiered, episodic + semantic split | Can its retrieval filter by label, and do its derived memories record their sources? | surveyed @ 0690078: strong atom lineage, physical per-store isolation, tags unused by any filter, Core mixes a whole store |
| [[Redis Agent Memory]] (Iris, managed; Agent Memory Server V0, open source) | Vector store RAG with working/long-term tiers | Can its search filters express label-subset checks inside the vector query? | surveyed: V0 yes (all/not_in tag pre-filters in KNN), lineage lost on merge, access not enforced; Iris a poor fit |
| [[Collaborative Memory]] (Rezazadeh et al. 2025) | Private + shared tiers with access control | How close is its access model to ours, and what should we borrow? | surveyed: read rule and provenance match ours; LLM declassifier on shared writes; derived items can lose labels; no code |
| [[Mem0]] | Vector store RAG (extracted facts; entity boost) | Do its filters pre-filter, and does UPDATE mix scopes or drop sources? | surveyed @ 8127e8b: real pre-filters; now add-only; no lineage; add-time lookup ignores labels; fork of 300–600 lines |
| [[Letta]] (formerly MemGPT) | Tiered / file-based (git-backed Markdown) | Can always-in-context memory blocks be kept per label set? | surveyed @ d7fd0a6: only as a directory per label set; no labels or local vector search; rewrites mix locations; poor base |
| [[Zep and Graphiti]] | Temporal knowledge graph | How do per-item labels work when entity nodes are shared across locations? | surveyed @ 47f6482: group_id only; graph walks check only end nodes; summaries mix all sources; deep fork |

## Policy engines

| Engine | Model | Question to answer | Status |
| --- | --- | --- | --- |
| Cedar | Attribute-based policies | Can policies over arbitrary context attributes return the allowed label set fast enough for every retrieval? | not surveyed |
| OPA / Rego | General policy-as-code | Is Rego's flexibility worth its cost for per-retrieval decisions? | not surveyed |
| OpenFGA / SpiceDB (Zanzibar-style) | Relationship-based | Can agent–environment–memory relations express label grants, or does ABAC fit better? | not surveyed |
| Hand-rolled rule table | Labels × attribute predicates | Is a small in-process rule set enough, before adopting an engine? | designed: [[Label Rule Table]] |
