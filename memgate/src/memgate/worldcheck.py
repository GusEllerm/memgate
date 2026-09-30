"""Check a world file before memgate uses it.

A world file lists the environments (and which memory types each lets be carried out), the
locations (each in one environment, some high assurance) and the agents. The host generates it from
its own model of the world; `memgate check-world` (and `memgate serve`, before starting) runs this.
"""

from __future__ import annotations

import json
from pathlib import Path

from memgate.context import PARTITION_SEP       # reserved in ids: partition bank names use it
from memgate.world import MEMORY_TYPES


def check_world(spec) -> list[str]:
    """Every problem with a world spec (the parsed JSON); empty when it is usable."""
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["the world must be a JSON object with environments, locations and agents"]
    unknown = set(spec) - {"environments", "locations", "agents"}
    if unknown:
        errors.append(f"unknown top-level keys: {sorted(unknown)}")

    def ids(kind: str, items) -> list[str]:
        out = []
        if not isinstance(items, list):
            errors.append(f"{kind} must be a list")
            return out
        for i, item in enumerate(items):
            ident = item.get("id") if isinstance(item, dict) else item if kind == "agents" else None
            if not isinstance(ident, str) or not ident:
                errors.append(f"{kind}[{i}]: needs a non-empty string id")
                continue
            if PARTITION_SEP in ident:
                errors.append(f"{kind}[{i}] {ident!r}: ids may not contain {PARTITION_SEP!r} (reserved for partitions)")
            out.append(ident)
        dupes = sorted({x for x in out if out.count(x) > 1})
        if dupes:
            errors.append(f"duplicate {kind} ids: {dupes}")
        return out

    envs = ids("environments", spec.get("environments", []))
    for e in spec.get("environments", []) if isinstance(spec.get("environments"), list) else []:
        if isinstance(e, dict) and "carry_out" in e:
            co = e["carry_out"]
            if not isinstance(co, list) or not all(isinstance(t, str) for t in co):
                errors.append(f"environment {e.get('id')!r}: carry_out must be a list of memory types")
            elif set(co) - MEMORY_TYPES:
                errors.append(f"environment {e.get('id')!r}: unknown memory types {sorted(set(co) - MEMORY_TYPES)} "
                              f"(known: {sorted(MEMORY_TYPES)})")
        if isinstance(e, dict) and set(e) - {"id", "carry_out"}:
            errors.append(f"environment {e.get('id')!r}: unknown keys {sorted(set(e) - {'id', 'carry_out'})}")

    ids("locations", spec.get("locations", []))
    for l in spec.get("locations", []) if isinstance(spec.get("locations"), list) else []:
        if not isinstance(l, dict):
            continue
        if l.get("environment") not in envs:
            errors.append(f"location {l.get('id')!r}: environment {l.get('environment')!r} is not listed")
        if "high_assurance" in l and not isinstance(l["high_assurance"], bool):
            errors.append(f"location {l.get('id')!r}: high_assurance must be true or false")
        if set(l) - {"id", "environment", "high_assurance"}:
            errors.append(f"location {l.get('id')!r}: unknown keys {sorted(set(l) - {'id', 'environment', 'high_assurance'})}")

    agents = spec.get("agents", [])
    if isinstance(agents, list) and not all(isinstance(a, str) for a in agents):
        errors.append("agents must be a list of agent id strings")
    else:
        ids("agents", agents)
    if not spec.get("locations"):
        errors.append("the world has no locations")
    if not spec.get("agents"):
        errors.append("the world has no agents")
    return errors


def check_world_file(path: str | Path) -> list[str]:
    try:
        spec = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        return [f"cannot read {path}: {e}"]
    return check_world(spec)
