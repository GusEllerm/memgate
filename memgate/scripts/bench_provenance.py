"""Synthetic load for the provenance log: recording throughput and query latency.

    .venv/bin/python scripts/bench_provenance.py --turns 10000 100000

A world of agents in a few locations. Each turn: the speaker recalls up to 20 earlier memories,
speaks, and a memory is formed from the turn; every tenth memory is also a consolidation derived
from three earlier memories. Queries are timed on randomly chosen recent memories.
"""

from __future__ import annotations

import argparse
import random
import statistics
import tempfile
import time

from memgate.derivation import conversation_labels
from memgate.policy import Policy
from memgate.provenance import ProvenanceLog
from memgate.registry import Registry
from memgate.world import World


def build(turns: int, seed: int = 7):
    rng = random.Random(seed)
    w = World()
    w.add_environment("campus")
    locs = [f"room{i}" for i in range(8)]
    for l in locs:
        w.add_location(l, "campus")
    agents = [f"a{i}" for i in range(100)]
    w.add_agents(*agents)
    reg = Registry()
    log = ProvenanceLog(tempfile.mkdtemp(prefix="provbench-"), w)
    writes: list[tuple[str, str]] = []
    t0 = time.perf_counter()
    for n in range(turns):
        loc = rng.choice(locs)
        people = rng.sample(agents, rng.randint(2, 4))
        labels = conversation_labels(loc, people)
        ls = reg.register(labels)
        recalled = rng.sample(writes[-2000:], min(20, len(writes[-2000:]))) if writes else []
        rid = log.record_recall(people[0], loc, "q", {ls}, recalled)
        tid = log.record_turn(people[0], loc, people, "said something", [rid])
        wid = f"w{n}"
        derived = [x for x, _ in rng.sample(writes[-500:], 3)] if n % 10 == 9 and len(writes) > 3 else []
        log.record_write(wid, people[0], loc, ls, "conversation", "memory text", turns=[tid], derived_from=derived)
        writes.append((wid, ls))
    elapsed = time.perf_counter() - t0
    return w, reg, log, writes, elapsed, rng


def timed(fn, reps: int = 50) -> float:
    xs = []
    for _ in range(reps):
        t = time.perf_counter()
        fn()
        xs.append(time.perf_counter() - t)
    return statistics.median(xs) * 1000


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--turns", type=int, nargs="+", default=[10000])
    args = p.parse_args()
    for turns in args.turns:
        w, reg, log, writes, elapsed, rng = build(turns)
        with log._read_conn(["shared"]) as db:
            edges = sum(db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                        for t in ("used", "informed_by", "generated_by", "derived_from", "associated_with"))
        size = sum(f.stat().st_size for f in log.root.glob("*.sqlite*")) / 1e6
        pol = Policy(w, reg)
        pick = lambda: rng.choice(writes[-1000:])[0]
        early = lambda: rng.choice(writes[:1000])[0]
        print(f"\n{turns:,} turns: {edges:,} edge rows, {size:.0f} MB on disk")
        print(f"  record: {3 * turns / elapsed:,.0f} events/s ({elapsed / turns * 1000:.2f} ms per recall+turn+write)")
        print(f"  sources_of (1 step)          {timed(lambda: log.sources_of(pick(), ['shared'])):7.2f} ms")
        print(f"  ancestors (depth 3)          {timed(lambda: log.ancestors(pick(), ['shared'], 3)):7.2f} ms")
        print(f"  ancestors (depth 10)         {timed(lambda: log.ancestors(pick(), ['shared'], 10), 10):7.2f} ms")
        print(f"  descendants of an early memory (depth 3) {timed(lambda: log.descendants(early(), depth=3), 10):7.2f} ms")
        print(f"  exposure (one agent)         {timed(lambda: log.exposure(rng.choice(sorted(w.agents))), 20):7.2f} ms")
        print(f"  flows (one label set)        {timed(lambda: log.flows(rng.choice(writes)[1]), 10):7.2f} ms")
        print(f"  trail for an asker (depth 3) {timed(lambda: log.trail(pick(), 'a1', 'room1', pol), 10):7.2f} ms  "
              f"({len(reg):,} label sets)")


if __name__ == "__main__":
    main()
