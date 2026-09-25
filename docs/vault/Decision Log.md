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
| 2026-09-25 | What counts as a "context" in the host project: a task, a user, a conversation, a tool, or a combination? | | open | Shapes [[Context-Scoped Memory Permissions]]. |
| 2026-09-25 | Are locks strictly hierarchical (nested scopes), or can contexts overlap arbitrarily? | | open | |
| 2026-09-25 | Must locked memory be hidden entirely, or may the agent know it exists? | Hidden entirely: filtered before it reaches the prompt (Claude) | proposed | The "enforcement below the model" requirement assumes this. |
| 2026-09-25 | Is the host project tied to a language, framework or model provider? | | open | Constrains the candidates in [[Architecture Survey]]. |
| 2026-09-25 | Repo visibility | Private (Claude) | proposed | Created private on GitHub as GusEllerm/agentic-memory. |
