---
type: design
status: draft
authority: describes
summary: "The rubric each candidate memory architecture is scored against (1–5 per criterion), derived from the draft requirements."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, design, evaluation]
---

# Evaluation Criteria

*Draft 2026-09-25, derived from [[Context-Scoped Memory Permissions]]. Scores go in [[Architecture Survey]].*

Each candidate is scored 1–5 per criterion.

| Criterion | What a 5 looks like |
| --- | --- |
| Permission granularity | Locks attach to single memory items |
| Enforcement point | Locked items are filtered before retrieval results exist |
| Derived-data safety | Summaries and embeddings inherit source locks automatically |
| Unlock/lock latency | Context switches change access with no re-indexing |
| Retrieval quality | Recall is no worse than the unpermissioned baseline |
| Auditability | Every access is attributable to a context |
| Implementation cost | Works with off-the-shelf components |
