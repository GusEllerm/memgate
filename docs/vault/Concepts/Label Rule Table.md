---
type: design
status: draft
authority: describes
summary: "Minimal permission layer: rules over context attributes grant labels; an item is readable only if all its labels are granted; derived items carry the union of their sources' labels; enforced as a label-set-ID filter inside vector search."
created: 2026-09-25
updated: 2026-09-25
tags: [agentic-memory, design, permissions, policy]
---

# Label Rule Table

*Draft 2026-09-25. Claude's design for the "hand-rolled rule table" baseline in [[Architecture Survey]]; the choices marked (proposed) are rows in [[Decision Log]] and carry no authority until Gus rules. Builds on [[Context-Scoped Memory Permissions]] and [[Vector Store Label Filtering]].*

**The idea.** A rule is a condition on context attributes that grants labels. The labels a context may read are the union of the grants from every matching rule, and anything not granted is denied. An item is readable only if **all** its labels are in that set. The check runs inside the vector search as a label-set-ID filter, so locked items never become candidates.

## Model

- **Context:** an open map of attributes, e.g. user, session, agent (or set of agents), environment. New attributes need no schema change.
- **Rule:** a condition on attributes (equality, set membership, AND) that grants labels, with separate grants for reading and for writing. Example: agent in {planner, critic} AND environment = lab-A grants read on {project-x, lab-A}.
- **Allowed set:** the union of read grants from all matching rules. Default deny.
- **Item check (accepted):** item labels ⊆ allowed set. "Any label allowed" would let through an item tagged with one allowed and one locked label.
- **Unlabelled items (open):** proposed that every item carries at least one label. Gus asked how that fits with an agent's personal memory; see [[Label and Memory Types]].

## Enforcement

1. Evaluate the rules against the context to get the allowed set.
2. Map it to the IDs of the stored label sets that are subsets of it (accepted). This works on every store; see [[Vector Store Label Filtering]].
3. Put label-set ID IN [...] inside the vector query as a pre-filter. Never filter after the search.
4. Log the context attributes, matched rules, allowed set and returned item IDs, to meet the audit requirement.

## Derived data

- **Union inheritance (accepted as default):** a summary, consolidated fact or embedding carries the union of its sources' labels. Gus requires that propagation can be relaxed per label type; see [[Label and Memory Types]]. It is produced in a context that unlocks all of them, and never merged across label sets unless the union is acceptable.
- **Embeddings** carry their item's labels exactly. Inversion attacks make them as sensitive as the text.
- **Later refinement:** labelling by the inputs that actually influenced the output (permissive information-flow control) could replace the union and unlock more.

## Visibility headroom

Each grant carries a visibility mode, which for now is always "hidden". Later, a label could grant "existence visible" and return a stub instead of the content, without changing the filter. That meets Gus's condition on the hidden-by-default ruling.

## Known gaps

- **Side channels:** keyword ranking statistics (IDF) and semantic or KV caches must be computed per allowed set, or not shared across contexts. Otherwise locked content leaks through scores and timing. Hybrid search (as in Falda and Redis) is exposed to this. See [[Vector Store Label Filtering]].
- **Growth of label-set IDs:** cost scales with the label sets actually in use. Needs measuring at the scale of the host project.
