---
type: design
status: draft
authority: describes
summary: "The problem this project researches: an agent's memory where the active context unlocks and locks slices of it at a fine grain, and the draft requirements a memory system must meet."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, design, permissions]
---

# Context-Scoped Memory Permissions

*Draft 2026-09-25. The requirements below are Claude's first reading of Gus's brief and carry no authority until confirmed; open points are rows in [[Decision Log]].*

## The problem

A host project needs an agent whose memory is permissioned at a fine grain. The current context, not the agent, decides which parts of memory are unlocked (readable, writable) and which stay locked. This project surveys agentic memory systems and recommends one that supports this. Candidates are in [[Architecture Survey]]; they are scored with [[Evaluation Criteria]].

## Draft requirements

- **Context-triggered unlock/lock.** Entering a context grants access to a scoped slice of memory; leaving it revokes access.
- **Fine granularity.** Permissions attach to individual memory items or small groups, not whole stores.
- **Enforcement below the model.** Locked memory is filtered at retrieval, so it never reaches the prompt.
- **No leakage through derived data.** Summaries, embeddings and consolidated memories inherit their sources' locks.
- **Scoped writes.** New memories are tagged with the context that created them.
- **Auditability.** Every unlock, read and write is logged with the context that allowed it.
