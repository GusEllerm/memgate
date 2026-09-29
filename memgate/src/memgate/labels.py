"""Labels and label sets.

Three label kinds (docs/vault/Concepts/Label and Memory Types.md):
- self:A   identity, the owner of a personal memory; all must be held
- loc:L    the conceptual location a memory was formed in; all must be held
- with:X   a participant present when the memory was formed; the reader must be one of them

A label set is the full set of labels on a memory. Its ID is content-addressed, so every store
and process agrees on it without coordination, and a memory system only ever sees the opaque ID.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Literal

Kind = Literal["self", "loc", "with"]
KINDS: tuple[Kind, ...] = ("self", "loc", "with")

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

    def __str__(self) -> str:
        return f"{self.kind}:{self.value}"

    @classmethod
    def parse(cls, text: str) -> "Label":
        kind, _, value = text.partition(":")
        return cls(kind, value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class LabelSet:
    labels: frozenset[Label]

    @classmethod
    def of(cls, labels: Iterable[Label | str]) -> "LabelSet":
        return cls(frozenset(l if isinstance(l, Label) else Label.parse(l) for l in labels))

    @classmethod
    def build(cls, *, selfs: Iterable[str] = (), locs: Iterable[str] = (), withs: Iterable[str] = ()) -> "LabelSet":
        return cls.of([Label("self", v) for v in selfs] + [Label("loc", v) for v in locs] + [Label("with", v) for v in withs])

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
    def key(self) -> str:
        return "|".join(sorted(str(l) for l in self.labels))

    @property
    def id(self) -> str:
        return "ls_" + hashlib.sha256(self.key.encode()).hexdigest()[:16]

    def __str__(self) -> str:
        return "{" + ", ".join(sorted(str(l) for l in self.labels)) + "}"
