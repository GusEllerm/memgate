---
type: reference
status: active
authority: reference
summary: "Candidate agentic memory architectures, the permission question each raises, and their scores against the evaluation criteria. None surveyed yet."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, reference, survey]
---

# Architecture Survey

*As of 2026-09-25 no candidate has been surveyed. Each gets its own `Reference/` note when it is, linked from its row. Scored with [[Evaluation Criteria]].*

| Architecture | Where memory lives | Permission question to answer | Status |
| --- | --- | --- | --- |
| Vector store RAG | Embeddings + metadata | Can metadata filters enforce locks at query time without leaking via similarity? | not surveyed |
| Knowledge graph | Nodes and edges | Can locks apply per node/edge, and do traversals respect them? | not surveyed |
| Tiered / OS-style (core, recall, archival) | Paged in and out of context | Does paging map cleanly onto unlock and lock events? | not surveyed |
| Episodic + semantic split | Raw episodes plus distilled facts | Do distilled facts inherit the locks of their source episodes? | not surveyed |
| File / document based | Files the agent reads and writes | Can filesystem-style ACLs serve as the permission layer? | not surveyed |
| Hybrid | Several of the above | Is one policy engine enforceable across all stores? | not surveyed |
