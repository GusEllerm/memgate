---
type: decision-log
status: active
authority: log
summary: "Decisions and open questions for agentic-memory. Only Gus moves a row from open or proposed to accepted."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory]
---

# Decision Log

Rows are open or proposed until Gus accepts them. Agent recommendations are marked as such and carry no authority.

| Date | Question | Proposal (by) | Status | Notes |
|---|---|---|---|---|
| 2026-09-25 | What counts as a "context" in the host project: a task, a user, a conversation, a tool, or a combination? | A combination of contextual attributes, open-ended: user/principal, conversation/session, which agent (or combination of agents), and the local environment the agent operates in; other attributes may be added (Gus) | accepted (Gus, 2026-09-25) | Gus: "combinations of agents, and which local context they are operating under (i.e. what 'environment' they are in) are interesting ways of saying agent has access to memories x, not y. Generally we want to be flexible in what contextual aspects can be used." The context model must be extensible, not a fixed set of fields. See [[Context-Scoped Memory Permissions]]. |
| 2026-09-25 | Are locks strictly hierarchical (nested scopes), or can contexts overlap arbitrarily? | Overlapping labels: memory items carry a set of labels, a context unlocks whatever its labels allow (Gus) | accepted (Gus, 2026-09-25) | Hierarchy can still be expressed as labels. Attribute-based (ABAC-like) rather than a scope tree. |
| 2026-09-25 | Must locked memory be hidden entirely, or may the agent know it exists? | Hidden entirely: filtered before it reaches the prompt (Claude) | accepted with condition (Gus, 2026-09-25) | Condition: only if per-item configurability (existence visible, content locked) can be added later without redesign. Candidates are checked for this. |
| 2026-09-25 | Is the host project tied to a language, framework or model provider? | Not tied yet (Gus) | accepted (Gus, 2026-09-25) | Survey candidates on merit; stack decided later. |
| 2026-09-25 | Repo visibility | Private (Claude) | accepted (Gus, 2026-09-25) | Private for now, as GusEllerm/agentic-memory. |
| 2026-09-25 | Survey shape: given attribute-based contexts and overlapping labels, is the permission layer part of the memory system or separate? | Treat it as two layers surveyed separately: memory stores (judged on label-filtered retrieval and derived-data lineage) and policy engines that map context attributes to labels (Claude) | accepted (Gus, 2026-09-25) | Follows from the two accepted rows above. Trade-off: stores with built-in permissions get no extra credit. Policy engines are the second table in [[Architecture Survey]]. |
