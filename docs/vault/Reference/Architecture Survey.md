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
| [[Falda]] (UChicago, Rick Stevens' group) | Tiered, episodic + semantic split | Can its retrieval filter by label, and do its derived memories record their sources? | surveyed: strong provenance, coarse store-per-pool isolation, no per-item filter yet |
| [[Redis Agent Memory]] (Iris, managed; Agent Memory Server V0, open source) | Vector store RAG with working/long-term tiers | Can its search filters express label-subset checks inside the vector query? | surveyed: V0 yes (all/not_in tag pre-filters in KNN), lineage lost on merge, access not enforced; Iris a poor fit |

## Policy engines

| Engine | Model | Question to answer | Status |
| --- | --- | --- | --- |
| Cedar | Attribute-based policies | Can policies over arbitrary context attributes return the allowed label set fast enough for every retrieval? | not surveyed |
| OPA / Rego | General policy-as-code | Is Rego's flexibility worth its cost for per-retrieval decisions? | not surveyed |
| OpenFGA / SpiceDB (Zanzibar-style) | Relationship-based | Can agent–environment–memory relations express label grants, or does ABAC fit better? | not surveyed |
| Hand-rolled rule table | Labels × attribute predicates | Is a small in-process rule set enough, before adopting an engine? | designed: [[Label Rule Table]] |
