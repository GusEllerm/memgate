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

*Draft 2026-09-25. Requirements marked (accepted) follow rulings in [[Decision Log]]; the rest are Claude's draft and carry no authority until confirmed.*

## The problem

A host project needs an agent whose memory is permissioned at a fine grain. The current context, not the agent, decides which parts of memory are unlocked (readable, writable) and which stay locked. This project surveys agentic memory systems and recommends one that supports this. Candidates are in [[Architecture Survey]]; they are scored with [[Evaluation Criteria]].

## What a context is (accepted)

A context is a combination of attributes, and the set of attributes is open-ended. Known attributes so far:

- the user or principal the agent acts for
- the conversation or session
- which agent is acting, or which combination of agents
- the local environment the agent is operating in

A permission is a rule over some combination of these, for example: agent A in environment E may read memories x, not y. New attributes (a context item z) must be addable without redesigning the model.

## Requirements

- **Context-triggered unlock/lock.** Entering a context grants access to a slice of memory; leaving it revokes access.
- **Overlapping labels (accepted).** Memory items carry a set of labels; a context unlocks whatever labels its rules allow. Scopes can overlap; a hierarchy is expressible as labels but not required.
- **Extensible context attributes (accepted).** Rules can reference any context attribute, including ones added later.
- **Fine granularity.** Permissions attach to individual memory items or small groups, not whole stores.
- **Hidden by default (accepted, with condition).** Locked memory is filtered at retrieval, so it never reaches the prompt and the agent cannot tell it exists. Condition: the design must allow per-item "existence visible, content locked" later without a redesign, so visibility should be an output of the policy rather than hard-wired into the filter.
- **No leakage through derived data.** Summaries, embeddings and consolidated memories inherit their sources' locks.
- **Scoped writes.** New memories are tagged with the context that created them.
- **Auditability.** Every unlock, read and write is logged with the context that allowed it.
