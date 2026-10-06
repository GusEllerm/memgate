"""memgate: context-scoped permissions for agent memory.

    from memgate import Context, Gate
    from memgate.adapters.hindsight import HindsightMemory      # Memory over the Hindsight store; see memgate.store for others

    gate = Gate.from_env()                                   # MEMGATE_WORLD, MEMGATE_REGISTRY, MEMGATE_SECRET
    mem = HindsightMemory(gate, bank="ranch", base_url="http://127.0.0.1:8889")
    here = Context(agent="ada", location="lab", participants=("ada", "bo"))   # built by the host, verified
    mem.remember(here, "Bo said the lab safe combination is 4471.")
    mem.recall(here, "lab safe combination")

See INTEGRATION.md for the contract with the host.
"""

from memgate.context import Context, Gate, load_world
from memgate.core import AsyncMemory, Memory, Recalled, RecallBatch
from memgate.labels import CLASSES, Label, LabelSet, NOBODY
from memgate.store import Capabilities, Hit, Item, Listed, Store
from memgate.world import ClassPolicy, Environment, Location, World

__version__ = "0.6.0"

__all__ = ["Context", "Gate", "load_world", "Label", "LabelSet", "NOBODY", "CLASSES", "Environment", "Location", "World",
           "ClassPolicy", "Memory", "AsyncMemory", "Recalled", "RecallBatch", "Store", "Capabilities", "Item", "Hit", "Listed"]
