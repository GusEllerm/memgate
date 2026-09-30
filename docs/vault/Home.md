# Agentic Memory Research

This vault is the long-term memory for **memgate** (the repo was called agentic-memory until 2026-09-30). Agents and people write it as the code takes shape;
`livedocs` keeps the notes honest: every note that names code in backticks is bound to that code, and a
commit that changes the code is blocked until the note is updated or acknowledged.

## Where things go

| Folder | Holds | Checked against code? |
|---|---|---|
| `Modules/` | one note per module or package: what it does, how it works, what depends on it | yes |
| `Concepts/` | ideas that span modules: an architecture, a lifecycle, an invariant | yes, where they name code |
| `Reference/` | external facts, surveys, dated reviews | reviews (`Review *`) are snapshots |
| `Sessions/` | one log per working session | snapshots (never checked) |
| `Templates/` | note templates (the Templates core plugin points here) | — |

## How to write a note that stays true

- Name code in backticks: `` `module.function()` ``, `` `ClassName` ``, `` `path/to/file.py` ``. Those are the
  claims livedocs checks. Prose that names no code is not checked (and is reported as such).
- Commit the note; the commit stamps it. There is nothing else to run.
- When a commit is blocked, the message shows *was / now* for the code that changed and the note lines
  that mention it. Edit the note and commit again, or `livedocs stamp <note> --ack --reason "…"` if the
  note is still right.
- Dated records go in `Sessions/` or are named `Reference/Review …`; they are snapshots and never block.

## Map

- [[Decision Log]]: open questions and rulings
- [[Context-Scoped Memory Permissions]]: the problem and draft requirements
- [[Modules]] · [[Concepts]] · [[Reference]] · [[Sessions]]
