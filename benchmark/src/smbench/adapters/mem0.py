"""Mem0 (open source) adapter: in-process Memory with local Qdrant and fastembed."""

from __future__ import annotations

import importlib.metadata
import os
from pathlib import Path

os.environ.setdefault("MEM0_TELEMETRY", "false")

import mem0.configs.prompts as _mem0_prompts  # noqa: E402
from mem0 import Memory as Mem0Memory  # noqa: E402

from smbench.adapters import EMBEDDER, EMBEDDING_DIMS, Memory, Session  # noqa: E402


# Mem0's extraction prompt anchors relative dates ("yesterday") to a current/observation date. The
# prompt builder accepts one, but the OSS add() never passes it, so it falls back to today's wall
# clock. We supply the session date during each add(), which is what the Mem0 Platform's
# `timestamp` parameter does.
_session_date: str | None = None
_resolve_dates = _mem0_prompts._resolve_dates


def _resolve_session_dates(current_date=None, observation_date=None):
    if _session_date is not None:
        current_date = current_date or _session_date
        observation_date = observation_date or _session_date
    return _resolve_dates(current_date, observation_date)


_mem0_prompts._resolve_dates = _resolve_session_dates


class Mem0Adapter:
    name = "mem0"

    def __init__(self, run_id: str, gateway: str, model: str, root: Path = Path("results/mem0")):
        store = root / run_id
        store.mkdir(parents=True, exist_ok=True)
        self.config = {
            "llm": {"provider": "openai", "config": {
                "model": model, "openai_base_url": gateway, "api_key": "gateway", "temperature": 0.0,
                # Mem0's default of 2000 truncates gpt-oss-120b (reasoning tokens count) on full sessions.
                "max_tokens": 8000}},
            "embedder": {"provider": "fastembed", "config": {"model": EMBEDDER}},
            "vector_store": {"provider": "qdrant", "config": {
                "collection_name": "locomo", "path": str(store / "qdrant"), "embedding_model_dims": EMBEDDING_DIMS}},
            "history_db_path": str(store / "history.db"),
        }
        self.memory = Mem0Memory.from_config(self.config)

    def ingest_session(self, session: Session) -> None:
        a, b = session.speakers
        messages = [{"role": "user" if t.speaker == a else "assistant", "content": f"{t.speaker}: {t.text}"}
                    for t in session.turns]
        messages.insert(0, {"role": "user", "content": f"[{session.when_text}] New conversation session between {a} and {b}."})
        # The OSS SDK rejects `timestamp`; the session date reaches extraction via _resolve_session_dates.
        global _session_date
        _session_date = session.when.date().isoformat()
        try:
            self.memory.add(messages, user_id=session.conversation_id,
                            metadata={"session": session.index, "date": session.when_text})
        finally:
            _session_date = None

    def finalize(self, conversation_id: str) -> None:
        return None

    def search(self, conversation_id: str, query: str, k: int) -> list[Memory]:
        res = self.memory.search(query, top_k=k, filters={"user_id": conversation_id})
        out = []
        for r in res.get("results", []):
            md = r.get("metadata") or {}
            out.append(Memory(text=r["memory"], when=md.get("date")))
        return out

    def describe(self) -> dict:
        return {"system": "mem0", "mem0ai": importlib.metadata.version("mem0ai"),
                "fastembed": importlib.metadata.version("fastembed"), "embedder": EMBEDDER,
                "ingest": "one add() per session (speaker A as user, B as assistant; names kept in text); "
                          "extraction's current/observation date set to the session date (as the Platform's timestamp does)",
                "llm_max_tokens": 8000,
                "search": "search top_k=k filtered by user_id=conversation"}
