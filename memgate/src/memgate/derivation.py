"""Labels for new and derived memories, and the rule that keeps consolidation within a label set.

- A memory formed in a conversation carries the location and every participant present.
- A derived memory must be readable only by someone who could read every source: identity and
  location labels combine (union), participant labels narrow to the agents common to every source
  (intersection). If the sources share no participant, the result carries NOBODY and no one reads it
  through participation. (docs/vault/Decision Log.md, 2026-09-25)
- Merging, deduplication and consolidation happen only within one label set. The only way across is
  an explicit carry-out into personal memory, which the environment must allow (Policy.may_carry_out).
"""

from __future__ import annotations

from typing import Iterable

from memgate.labels import NOBODY, LabelSet, strictest


class CrossLabelSetMerge(ValueError):
    """Raised when a merge, dedup or consolidation would combine memories from different label sets."""


def conversation_labels(location: str, participants: Iterable[str]) -> LabelSet:
    """Labels for a memory formed in a conversation at `location` among `participants`."""
    people = sorted(set(participants))
    if not people:
        raise ValueError("a conversation memory needs at least one participant")
    return LabelSet.build(locs=[location], withs=people)


def personal_labels(agent: str, cls: str | None = None) -> LabelSet:
    """Labels for an agent's personal memory: readable by the agent everywhere. With a class (one of
    `labels.CLASSES`), a separate personal set, {self:A, class:C}: read exactly like {self:A}, but a
    different label set, so the memory system never consolidates the two together."""
    return LabelSet.build(selfs=[agent], classes=[cls] if cls else [])


def personal_note_labels(agent: str, location: str) -> LabelSet:
    """A personal note kept inside a location, e.g. a high-assurance one: readable by the agent, there only."""
    return LabelSet.build(selfs=[agent], locs=[location])


def derived_labels(sources: Iterable[LabelSet]) -> LabelSet:
    sources = list(sources)
    if not sources:
        raise ValueError("a derived memory needs at least one source")
    selfs = set().union(*(s.selfs for s in sources))
    locs = set().union(*(s.locs for s in sources))
    constrained = [s.withs for s in sources if s.withs]
    withs: set[str] = set.intersection(*(set(w) for w in constrained)) if constrained else set()
    if constrained and not withs:
        withs = {NOBODY}
    # A derived memory is at least as strict as its strictest source (a class needs a self, which the
    # union above keeps, since a classed source always has one).
    cls = strictest(set().union(*(s.classes for s in sources)))
    return LabelSet.build(selfs=selfs, locs=locs, withs=withs, classes=[cls] if cls else [])


def check_merge(label_set_ids: Iterable[str]) -> str:
    """Allow a merge only when every memory involved has the same label set; return that ID."""
    ids = set(label_set_ids)
    if len(ids) != 1:
        raise CrossLabelSetMerge(f"merge across {len(ids)} label sets is not allowed: {sorted(ids)}")
    return ids.pop()
