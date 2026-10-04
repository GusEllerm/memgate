---
type: module
status: active
authority: describes
summary: "benchmark/src/smbench/speed: timings of memgate's decisions with no LLM and no store. cedar.py registers 1k to 1M label sets in worlds that grow alongside and times allowed_ids cold and warm, allowed_ids_exact (and checks it equals the compiled answer) and may_write."
created: 2026-10-04
updated: 2026-10-04
tags: [memgate, benchmark, speed]
---

# Speed Suite

Plan §3 of the [[Benchmark Plan]]: how fast memgate decides, measured without an LLM or a memory store. Results: [[Review Speed Cedar 2026-10-01]].

## What it is

- **`benchmark/src/smbench/speed/cedar.py`**, run as `python -m smbench.speed.cedar --out results/speed/<run> [--sizes ...]` in an environment with memgate and cedarpy (`.venvs/hindsight`, with `PYTHONPATH=src`).
- `SHAPES` maps a registry size (1k, 10k, 100k, 1M label sets) to a world (agents, locations, environments); `build_world` builds it with a quarter of locations high-assurance, and `label_sets` yields a realistic, distinct mix (80% conversations with 2 to 4 participants, 10% personal memory, 10% notes).
- `measure` registers the label sets in a fresh on-disk `Registry`, then times, for 20 random (agent, location) asks: `Policy.allowed_ids` on a fresh `Policy` (**cold**: partial evaluation plus the compiled query over the whole registry), the same `Policy` again after `TOP_UP` more label sets (**warm**: the incremental path), `Policy.allowed_ids_exact` up to `EXACT_LIMIT` (the reference answer, compared with the compiled one and reported as `compiled_matches_exact`), and `Policy.may_write`.
- `timed` reports median, p95, min and max in milliseconds. The report (`report.json`) records the machine, Python, cedarpy and memgate versions.
- `benchmark/tests/test_speed.py` runs `measure` at the smallest size and checks the compiled filter agrees with Cedar.

## Not yet in it

Filtered vector search inside Hindsight (tight and loose tag filters against exact search) and partition fan-out, the rest of plan §3; both need a populated store.
