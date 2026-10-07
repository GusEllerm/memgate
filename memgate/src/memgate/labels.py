"""Labels and label sets.

Five label kinds (docs/vault/Concepts/Label and Memory Types.md):
- self:A   identity, the owner of a personal memory; all must be held
- loc:L    the conceptual location a memory was formed in; all must be held
- with:X   a participant present when the memory was formed; the reader must be one of them
- class:C  (since 0.5.0) a class of personal memory, e.g. "unattributed": items kept under a rule
           (no one named) that must never be consolidated with the agent's other personal memory.
           Only alongside a self label, at most one per set, from the ordered list CLASSES. It decides
           nothing about who may read: the policies never see it. It only makes a separate label set,
           so the memory system keeps the class apart.
- src:S    (since 0.7.0) the location a personal memory was carried out of. Only alongside a self label.
           The policies read it: while S's environment lets nothing out (carry_out: []), a memory carried
           from S is recalled only in S (the source seal), evaluated against the world as it stands, so
           holding a location withholds at once and releasing it releases again. A separate label set
           per source also keeps the store from consolidating across locations.

A label set is the full set of labels on a memory. Its ID is content-addressed, so every store
and process agrees on it without coordination, and a memory system only ever sees the opaque ID.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Literal

Kind = Literal["self", "loc", "with", "class", "src"]
KINDS: tuple[Kind, ...] = ("self", "loc", "with", "class", "src")

# Classes of personal memory, least strict first. A memory never moves to a less strict class
# (the client refuses that carry-out), and an environment may set a minimum (World.min_class).
CLASSES: tuple[str, ...] = ("unattributed",)


def class_rank(cls: str | None) -> int:
    """0 for no class, then 1, 2, … along CLASSES. Raises ValueError for an unknown class."""
    if cls is None:
        return 0
    if cls not in CLASSES:
        raise ValueError(f"unknown memory class {cls!r} (known: {list(CLASSES)})")
    return CLASSES.index(cls) + 1


def strictest(classes) -> str | None:
    """The strictest of some classes (None for none)."""
    return max(classes, key=class_rank, default=None)

# A participant label no agent can hold. It marks a derived memory whose sources share no
# participant, so the participant check fails for every reader instead of being skipped.
NOBODY = "∅"


@dataclass(frozen=True, order=True)
class Label:
    kind: Kind
    value: str

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown label kind {self.kind!r}")
        if not self.value or "|" in self.value:
            raise ValueError(f"label value must be non-empty and contain no '|': {self.value!r}")
        if self.kind == "class":
            class_rank(self.value)                     # raises for a class this version doesn't know

    def __str__(self) -> str:
        return f"{self.kind}:{self.value}"

    @classmethod
    def parse(cls, text: str) -> "Label":
        kind, _, value = text.partition(":")
        return cls(kind, value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class LabelSet:
    labels: frozenset[Label]

    def __post_init__(self) -> None:
        classes = [l for l in self.labels if l.kind == "class"]
        if classes and not any(l.kind == "self" for l in self.labels):
            raise ValueError(f"a class label needs a self label beside it: {sorted(str(l) for l in self.labels)}")
        if len(classes) > 1:
            raise ValueError(f"at most one class per label set: {sorted(str(l) for l in classes)}")
        if any(l.kind == "src" for l in self.labels) and not any(l.kind == "self" for l in self.labels):
            raise ValueError(f"a source label needs a self label beside it: {sorted(str(l) for l in self.labels)}")

    @classmethod
    def of(cls, labels: Iterable[Label | str]) -> "LabelSet":
        return cls(frozenset(l if isinstance(l, Label) else Label.parse(l) for l in labels))

    @classmethod
    def build(cls, *, selfs: Iterable[str] = (), locs: Iterable[str] = (), withs: Iterable[str] = (),
              classes: Iterable[str] = (), srcs: Iterable[str] = ()) -> "LabelSet":
        return cls.of([Label("self", v) for v in selfs] + [Label("loc", v) for v in locs] + [Label("with", v) for v in withs]
                      + [Label("class", v) for v in classes] + [Label("src", v) for v in srcs])

    def values(self, kind: Kind) -> frozenset[str]:
        return frozenset(l.value for l in self.labels if l.kind == kind)

    @property
    def selfs(self) -> frozenset[str]:
        return self.values("self")

    @property
    def locs(self) -> frozenset[str]:
        return self.values("loc")

    @property
    def withs(self) -> frozenset[str]:
        return self.values("with")

    @property
    def classes(self) -> frozenset[str]:
        return self.values("class")

    @property
    def srcs(self) -> frozenset[str]:
        return self.values("src")

    @property
    def key(self) -> str:
        return "|".join(sorted(str(l) for l in self.labels))

    @property
    def id(self) -> str:
        return "ls_" + hashlib.sha256(self.key.encode()).hexdigest()[:16]

    def __str__(self) -> str:
        return "{" + ", ".join(sorted(str(l) for l in self.labels)) + "}"
