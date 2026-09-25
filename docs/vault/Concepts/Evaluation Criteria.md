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

Each candidate is scored 1–5 per criterion. Memory stores and policy engines are scored separately ([[Architecture Survey]]); a criterion that doesn't apply to a layer is left out of that layer's scores.

| Criterion | What a 5 looks like |
| --- | --- |
| Permission granularity | Locks attach to single memory items |
| Enforcement point | Locked items are filtered before retrieval results exist |
| Derived-data safety | Summaries and embeddings inherit source locks automatically |
| Unlock/lock latency | Context switches change access with no re-indexing |
| Retrieval quality | Recall is no worse than the unpermissioned baseline |
| Auditability | Every access is attributable to a context |
| Context extensibility | New context attributes can be used in rules without re-indexing or schema changes |
| Visibility headroom | Per-item "existence visible, content locked" can be added without redesign |
| Provenance | Every derived item links to its sources, including across agents, and merges never drop the links |
| Label-safe compaction | Forgetting, merging and summarising never mix label sets beyond what the environment allows |
| Export fidelity | Labels and provenance survive export, so training data can be filtered by them |
| Physical isolation option | A location can be given its own store without changing the API |
| Implementation cost | Works with off-the-shelf components; no stack lock-in (host stack is not fixed) |
