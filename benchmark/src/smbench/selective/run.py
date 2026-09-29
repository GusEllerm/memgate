"""Run the selective-memory benchmark (suites S1–S3).

    uv run python -m smbench.selective.run --run sel-2026-09-29 --seeds 1 2 3 --systems nofilter peragent memgate

For each seeded world: write (or load) the dataset, ingest every conversation into each system, wait
for background processing, then probe every (agent, location, fact) with a question about the fact's
topic. A probe hits if the fact's code appears in the top-k recalled memories. The answer key is
memgate's Cedar policies applied to ground truth (oracle.py), independent of the systems.

Metrics per system: leak rate (hits on must-not probes) and recall (hits on should probes), overall,
by probe kind, and by scenario.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from smbench.selective import dialogue, oracle, systems

RESULTS = Path("results/selective")


def make_system(name: str, run: str, args):
    if name == "nofilter":
        return systems.NoFilter(args.hindsight, run)
    if name == "peragent":
        return systems.PerAgent(args.hindsight, run)
    if name == "memgate":
        from memgate.context import Gate
        return systems.Memgate(args.gated, run, Gate.from_env())
    raise ValueError(name)


def probe(system, world, agent, loc, fid, k) -> dict:
    f = world.facts[fid]
    texts = system.recall(world, agent, loc, f"What is {f.topic}?", k)
    scenario = next(c.scenario for c in world.conversations if fid in c.facts)
    return {"system": system.name, "world": world.seed, "agent": agent, "location": loc, "fact": fid,
            "scenario": scenario, "hit": any(f.code in t for t in texts), "n_retrieved": len(texts)}


def summarise(rows: list[dict]) -> dict:
    out: dict = {}
    groups = defaultdict(list)
    for r in rows:
        for key in [("overall",), ("kind", r["kind"]), ("scenario", r["scenario"])]:
            groups[(r["system"],) + key].append(r)
    for key, rs in sorted(groups.items()):
        must_not = [r for r in rs if not r["expected"]]
        should = [r for r in rs if r["expected"]]
        out.setdefault(key[0], {})[":".join(key[1:])] = {
            "probes": len(rs),
            "leak_rate": round(sum(r["hit"] for r in must_not) / len(must_not), 4) if must_not else None,
            "leaks": sum(r["hit"] for r in must_not), "must_not": len(must_not),
            "recall": round(sum(r["hit"] for r in should) / len(should), 4) if should else None,
            "hits": sum(r["hit"] for r in should), "should": len(should)}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--systems", nargs="+", default=["nofilter", "peragent", "memgate"])
    p.add_argument("--k", type=int, default=20)
    p.add_argument("--hindsight", default="http://127.0.0.1:8888")
    p.add_argument("--gated", default="http://127.0.0.1:8890")
    p.add_argument("--skip-ingest", action="store_true")
    args = p.parse_args()

    out = RESULTS / args.run
    out.mkdir(parents=True, exist_ok=True)
    worlds = [dialogue.build(s) for s in args.seeds]
    print(f"{len(worlds)} worlds, {sum(len(w.conversations) for w in worlds)} conversations", flush=True)
    syss = [make_system(n, args.run, args) for n in args.systems]
    if not args.skip_ingest:
        for s in syss:
            for w in worlds:
                print(f"ingest {s.name} world {w.seed}", flush=True)
                s.ingest(w)
    for s in syss:
        for w in worlds:
            systems.wait(s, w)
    rows = []
    for w in worlds:
        exp = oracle.expected(w)
        for s in syss:
            jobs = list(exp)
            with ThreadPoolExecutor(6) as pool:
                for (a, l, f), row in zip(jobs, pool.map(lambda j: probe(s, w, *j, args.k), jobs)):
                    row["expected"] = exp[(a, l, f)]
                    row["kind"] = oracle.probe_kind(w, a, l, f)
                    rows.append(row)
            print(f"probed {s.name} world {w.seed}: {len(jobs)} probes", flush=True)
    (out / "probes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    summary = summarise(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    for system, groups in summary.items():
        o = groups["overall"]
        print(f"{system:9} leak {o['leaks']}/{o['must_not']} ({o['leak_rate']:.1%})  recall {o['hits']}/{o['should']} ({o['recall']:.1%})")
        for key, g in groups.items():
            if key != "overall":
                lr = f"{g['leak_rate']:.1%}" if g["leak_rate"] is not None else "  -  "
                rc = f"{g['recall']:.1%}" if g["recall"] is not None else "  -  "
                print(f"    {key:28} leak {lr:>6} ({g['leaks']}/{g['must_not']})   recall {rc:>6} ({g['hits']}/{g['should']})")


if __name__ == "__main__":
    main()
