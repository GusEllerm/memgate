---
type: design
status: draft
authority: describes
summary: "Discussion draft: personal memory as an identity-labelled compartment (so no item is unlabelled), label types that decide how strictly labels stick to derived memory, and memory types that decide which relaxations are allowed."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, design, permissions, memory-types]
---

# Label and Memory Types

*Discussion draft 2026-09-25. Claude's proposal in response to two questions Gus raised; nothing here is decided. The open rows are in [[Decision Log]]. Extends [[Label Rule Table]].*

## Personal memory without unlabelled items

Gus: if every memory needs a label, how does an agent keep its own personal memory? Personal memory must stay possible, because it is a way for agents to diversify.

**Proposal.**
- Every agent has an **identity label** (self:A) that is granted only in contexts where agent A is acting.
- A personal memory is written with self:A, so no item is ever unlabelled.
- Each agent's personal memory is a compartment only it can open. Two agents in the same role grow apart because their compartments differ.

**The catch.** Personal memory is not an escape hatch. Under union inheritance, A's reflection on project-x material carries {self:A, project-x}. A can then recall it only where project-x is also unlocked. Whether that is right depends on label types.

## Label types

Every label has a type. The read check is the same for all types: all of an item's labels must be allowed. Types differ in how the label **propagates** to derived memory.

| Type | Example | Propagation (proposed) | Why |
| --- | --- | --- | --- |
| Identity | self:A | Sticky on personal memory | The owner's compartment |
| Location / environment | env:lab-A | Sticky | Gus: an agent's conceptual location is more restrictive |
| Principal | user:alice | Sticky | Whose data it is |
| Participants | discussion:{A,B,C} | Relaxable | Gus: which agents were in a discussion is less restrictive |
| Session | session:42 | Relaxable | Sessions are short-lived |

- **Sticky:** always carried into derived items (the union default).
- **Relaxable:** may be dropped when deriving an item, but only under an explicit relaxation rule. The rule names the label type, the memory type being written and a condition on the context. Every relaxation is logged.

## Memory types

Memory types decide which relaxations are allowed:

| Memory type | Holds | Relaxation (proposed) |
| --- | --- | --- |
| Episodic | Raw events and turns | None: the raw record keeps every label |
| Semantic | Facts distilled from episodes | May drop participant and session labels |
| Procedural | Skills, how-tos, strategies | May drop participant and session labels; location is an open question |
| Personal / reflective | The agent's own conclusions | Adds self:A; sticky labels from its sources stay |

This lines up with Falda's tiers: T0 stream is episodic, T1 atoms are typed facts, patterns and preferences, and Core is a persona document. Mem0, Letta and Zep have their own taxonomies, which are not surveyed yet.

## Open questions for Gus

- [ ] Should an agent's personal memory be readable in **every** context where the agent acts (self:A alone)? Or only where its sources' sticky labels are also unlocked?
- [ ] Which label types exist, and which are sticky? The table above is a guess.
- [ ] Who decides a relaxation, a rule or a judgement? "This fact doesn't depend on who was in the discussion" is a judgement an LLM would make. That turns an LLM into a declassifier, which is the leakage path that FIDES and CaMeL guard against ([[Vector Store Label Filtering]]).
- [ ] Which memory type taxonomy? Adopt one from a surveyed system, or define our own.
