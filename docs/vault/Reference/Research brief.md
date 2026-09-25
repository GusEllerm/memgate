---
tags: [reference]
---
# Research brief

Survey agentic memory systems and recommend one for a host project where the active context
**unlocks** and **locks** parts of an agent's memory at a fine grain.

## Requirements (draft, to confirm against the host project)

- **Context-triggered unlock/lock:** entering a context grants access to a scoped slice of memory; leaving it revokes access.
- **Fine granularity:** permissions attach to individual memory items or small groups, not whole stores.
- **Enforcement below the model:** locked memory is filtered at retrieval, so it never reaches the prompt.
- **No leakage through derived data:** summaries, embeddings and consolidated memories inherit their sources' locks.
- **Scoped writes:** new memories are tagged with the context that created them.
- **Auditability:** every unlock, read and write is logged with the context that allowed it.

## Candidate architectures

| Architecture | Where memory lives | Permission question to answer |
| --- | --- | --- |
| Vector store RAG | Embeddings + metadata | Can metadata filters enforce locks at query time without leaking via similarity? |
| Knowledge graph | Nodes and edges | Can locks apply per node/edge, and do traversals respect them? |
| Tiered / OS-style (core, recall, archival) | Paged in and out of context | Does paging map cleanly onto unlock and lock events? |
| Episodic + semantic split | Raw episodes plus distilled facts | Do distilled facts inherit the locks of their source episodes? |
| File / document based | Files the agent reads and writes | Can filesystem-style ACLs serve as the permission layer? |
| Hybrid | Several of the above | Is one policy engine enforceable across all stores? |

## Evaluation criteria (score 1–5 per candidate)

| Criterion | What a 5 looks like |
| --- | --- |
| Permission granularity | Locks attach to single memory items |
| Enforcement point | Locked items are filtered before retrieval results exist |
| Derived-data safety | Summaries and embeddings inherit source locks automatically |
| Unlock/lock latency | Context switches change access with no re-indexing |
| Retrieval quality | Recall is no worse than the unpermissioned baseline |
| Auditability | Every access is attributable to a context |
| Implementation cost | Works with off-the-shelf components |

## Open questions

- [ ] What counts as a "context" in the host project: a task, a user, a conversation, a tool, or a combination?
- [ ] Are locks strictly hierarchical (nested scopes), or can contexts overlap arbitrarily?
- [ ] Must locked memory be hidden entirely, or may the agent know it exists?
- [ ] Is the host project tied to a language, framework or model provider?
