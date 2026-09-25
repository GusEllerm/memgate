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
| Vector store RAG | Embeddings + metadata | Can metadata filters enforce locks at query time without leaking via similarity? | not surveyed |
| Knowledge graph | Nodes and edges | Can locks apply per node/edge, and do traversals respect them? | not surveyed |
| Tiered / OS-style (core, recall, archival) | Paged in and out of context | Does paging map cleanly onto unlock and lock events? | not surveyed |
| Episodic + semantic split | Raw episodes plus distilled facts | Do distilled facts inherit the locks of their source episodes? | not surveyed |
| File / document based | Files the agent reads and writes | Can filesystem-style ACLs serve as the permission layer? | not surveyed |
| Hybrid | Several of the above | Is one policy engine enforceable across all stores? | not surveyed |

## Named systems

Specific systems, mapped to the families above.

| System | Family | Question to answer | Status |
| --- | --- | --- | --- |
| Falda (UChicago, Rick Stevens' group) | to be determined | Can its retrieval filter by label, and do its derived memories record their sources? | researching |
| Redis agent memory system | to be determined | Can its search filters express label-subset checks inside the vector query? | researching |

## Policy engines

| Engine | Model | Question to answer | Status |
| --- | --- | --- | --- |
| Cedar | Attribute-based policies | Can policies over arbitrary context attributes return the allowed label set fast enough for every retrieval? | not surveyed |
| OPA / Rego | General policy-as-code | Is Rego's flexibility worth its cost for per-retrieval decisions? | not surveyed |
| OpenFGA / SpiceDB (Zanzibar-style) | Relationship-based | Can agent–environment–memory relations express label grants, or does ABAC fit better? | not surveyed |
| Hand-rolled rule table | Labels × attribute predicates | Is a small in-process rule set enough, before adopting an engine? | not surveyed |
