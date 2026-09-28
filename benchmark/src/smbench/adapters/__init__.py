"""Memory-system adapters. Each one stores LoCoMo sessions and returns memories for a query.

Every adapter sends its LLM traffic through the ALCF gateway and uses the same local
embedder (BAAI/bge-small-en-v1.5), so the memory system is the only thing that varies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

EMBEDDER = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMS = 384


@dataclass
class Turn:
    speaker: str
    text: str
    dia_id: str


@dataclass
class Session:
    conversation_id: str
    index: int
    when: datetime
    when_text: str
    speakers: tuple[str, str]
    turns: list[Turn]

    def transcript(self) -> str:
        lines = [f"Conversation between {self.speakers[0]} and {self.speakers[1]}, session {self.index}, {self.when_text}."]
        lines += [f"{t.speaker}: {t.text}" for t in self.turns]
        return "\n".join(lines)


@dataclass
class Memory:
    text: str
    when: str | None = None

    def render(self) -> str:
        return f"[{self.when}] {self.text}" if self.when else self.text


class MemoryAdapter(Protocol):
    name: str

    def ingest_session(self, session: Session) -> None: ...

    def finalize(self, conversation_id: str) -> None:
        """Block until background processing (extraction, consolidation) has finished."""

    def search(self, conversation_id: str, query: str, k: int) -> list[Memory]: ...

    def describe(self) -> dict:
        """Versions and settings recorded with each run."""


def load_adapter(name: str, run_id: str, gateway: str, model: str) -> MemoryAdapter:
    if name == "hindsight":
        from smbench.adapters.hindsight import HindsightAdapter
        return HindsightAdapter(run_id=run_id)
    if name == "mem0":
        from smbench.adapters.mem0 import Mem0Adapter
        return Mem0Adapter(run_id=run_id, gateway=gateway, model=model)
    raise ValueError(f"unknown system {name!r}")
