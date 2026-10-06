"""Mem0 (open source, in process) as a memgate store. `pip install 'memgate[mem0]'`.

    from memgate.adapters.mem0 import Mem0Store
    mem = Memory(gate, Mem0Store(gate, path="/var/lib/memgate/mem0", llm=..., embedder=...), shared="ranch")
"""

from memgate.adapters.mem0.store import Mem0Store, filters_for  # noqa: F401
