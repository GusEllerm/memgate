"""Run the selective-memory benchmark (suites S1–S3).

    uv run python -m smbench.selective.run --run sel-2026-09-29 --seeds 1 2 3 --systems nofilter peragent memgate
    uv run python -m smbench.selective.run --run sel-env-indirect --banks-from sel-env-2026-09-30b --size env \
        --seeds 21 22 23 --probe indirect        # re-probe an earlier run's banks with harder questions

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
from smbench.selective.questions import question_for

RESULTS = Path("results/selective")


def make_system(name: str, run: str, args):
    if name == "nofilter":
        return systems.NoFilter(args.hindsight, run)
    if name == "peragent":
        return systems.PerAgent(args.hindsight, run)
    if name == "memgate":
        from memgate.context import Gate
        return systems.Memgate(args.gated, run, Gate.from_env())
    if name.startswith("mem0-"):                       # needs the mem0 environment (systems_mem0.py)
        from smbench.selective import systems_mem0
        if name == "mem0-nofilter":
            return systems_mem0.Mem0NoFilter(run)
        if name == "mem0-peragent":
            return systems_mem0.Mem0PerAgent(run)
        if name == "mem0-memgate":
            from memgate.context import Gate
            return systems_mem0.Mem0Memgate(run, Gate.from_env())
    raise ValueError(name)


def probe(system, world, agent, loc, fid, k, style: str = "direct") -> dict:
    f = world.facts[fid]
    texts = system.recall(world, agent, loc, question_for(world, fid, style), k)
    # Notes (S5) belong to no conversation.
    scenario = next((c.scenario for c in world.conversations if fid in c.facts), "S5")
    rank = next((i + 1 for i, t in enumerate(texts) if f.code in t), None)   # 1-based rank of the first hit
    return {"system": system.name, "world": world.seed, "agent": agent, "location": loc, "fact": fid,
            "scenario": scenario, "probe": style, "rank": rank, "hit": rank is not None, "n_retrieved": len(texts)}


MULTI = """I need two things. First: {q1} Second: {q2}"""


def multi_probes(world, exp: dict, rng, per_pair: int = 6) -> list[tuple[str, str, str, str]]:
    """Pairs of facts asked about in one question, per (agent, location): up to `per_pair` of them, spread
    over both-should, mixed and both-must-not pairs (a question that may be answered in part)."""
    out = []
    facts = list(world.facts)
    for agent in world.agents:
        for loc in world.locations:
            should = [f for f in facts if exp[(agent, loc, f)]]
            must_not = [f for f in facts if not exp[(agent, loc, f)]]
            kinds = []
            if len(should) >= 2:
                kinds += [("both-should", should, should)] * (per_pair // 3)
            if should and must_not:
                kinds += [("mixed", should, must_not)] * (per_pair // 3)
            if len(must_not) >= 2:
                kinds += [("both-must-not", must_not, must_not)] * (per_pair - 2 * (per_pair // 3))
            seen = set()
            for _, a, b in kinds:
                for _ in range(10):
                    f1, f2 = rng.choice(a), rng.choice(b)
                    if f1 != f2 and (f1, f2) not in seen and (f2, f1) not in seen:
                        seen.add((f1, f2))
                        out.append((agent, loc, f1, f2))
                        break
    return out


def probe_pair(system, world, agent, loc, f1, f2, k, exp: dict) -> list[dict]:
    """One question about two facts; one row per fact, so leak and recall count per fact as usual."""
    question = MULTI.format(q1=question_for(world, f1, "paraphrase"), q2=question_for(world, f2, "paraphrase"))
    texts = system.recall(world, agent, loc, question, k)
    pair_type = {(True, True): "both-should", (False, False): "both-must-not"}.get((exp[(agent, loc, f1)], exp[(agent, loc, f2)]), "mixed")
    rows = []
    for fid in (f1, f2):
        f = world.facts[fid]
        scenario = next((c.scenario for c in world.conversations if fid in c.facts), "S5")
        rank = next((i + 1 for i, t in enumerate(texts) if f.code in t), None)
        rows.append({"system": system.name, "world": world.seed, "agent": agent, "location": loc, "fact": fid,
                     "scenario": scenario, "probe": "multi", "pair": f"{f1}+{f2}", "pair_type": pair_type,
                     "rank": rank, "hit": rank is not None, "n_retrieved": len(texts)})
    return rows


def summarise(rows: list[dict]) -> dict:
    out: dict = {}
    groups = defaultdict(list)
    for r in rows:
        keys = [("overall",), ("kind", r["kind"]), ("scenario", r["scenario"])]
        if r.get("pair_type"):
            keys.append(("pair", r["pair_type"]))
        for key in keys:
            groups[(r["system"],) + key].append(r)
    for key, rs in sorted(groups.items()):
        must_not = [r for r in rs if not r["expected"]]
        should = [r for r in rs if r["expected"]]
        at5 = [r for r in should if r.get("rank") and r["rank"] <= 5]
        out.setdefault(key[0], {})[":".join(key[1:])] = {
            "probes": len(rs),
            "leak_rate": round(sum(r["hit"] for r in must_not) / len(must_not), 4) if must_not else None,
            "leaks": sum(r["hit"] for r in must_not), "must_not": len(must_not),
            "recall": round(sum(r["hit"] for r in should) / len(should), 4) if should else None,
            "recall_at_5": round(len(at5) / len(should), 4) if should else None,
            "hits": sum(r["hit"] for r in should), "should": len(should)}
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True)
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--size", choices=["small", "large", "env"], default="small")
    p.add_argument("--ingest-workers", type=int, default=4, help="stores in flight at once (the gateway still caps ALCF at 6)")
    p.add_argument("--systems", nargs="+", default=["nofilter", "peragent", "memgate"],
                   help="Hindsight: nofilter peragent memgate; Mem0 (run in .venvs/mem0): mem0-nofilter mem0-peragent mem0-memgate")
    p.add_argument("--k", type=int, default=20)
    p.add_argument("--hindsight", default="http://127.0.0.1:8888")
    p.add_argument("--gated", default="http://127.0.0.1:8890")
    p.add_argument("--skip-ingest", action="store_true")
    p.add_argument("--banks-from", help="probe the banks of this earlier run (implies --skip-ingest); results go to --run")
    p.add_argument("--probe", choices=["direct", "paraphrase", "indirect", "multi"], default="direct",
                   help="question style: direct names the topic; paraphrase and indirect come from questions.py; "
                        "multi asks about two facts at once (their paraphrases), sampled per agent and location")
    args = p.parse_args()
    if args.banks_from:
        args.skip_ingest = True

    out = RESULTS / args.run
    out.mkdir(parents=True, exist_ok=True)
    worlds = [dialogue.build(s, args.size) for s in args.seeds]
    print(f"{len(worlds)} worlds, {sum(len(w.conversations) for w in worlds)} conversations", flush=True)
    syss = [make_system(n, args.banks_from or args.run, args) for n in args.systems]
    if not args.skip_ingest:
        for s in syss:
            for w in worlds:
                jobs = s.ingest_jobs(w)
                print(f"ingest {s.name} world {w.seed}: {len(jobs)} stores", flush=True)
                with ThreadPoolExecutor(args.ingest_workers) as pool:
                    for i, _ in enumerate(pool.map(lambda j: j(), jobs), 1):
                        if i % 10 == 0 or i == len(jobs):
                            print(f"  {s.name} world {w.seed}: {i}/{len(jobs)} stored", flush=True)
    for s in syss:
        for w in worlds:
            systems.wait(s, w)
    rows, audit = [], []
    for w in worlds:
        exp = oracle.expected(w)
        for s in syss:
            # High-assurance probes first, bracketed by snapshots: recall there must change nothing.
            ha = [j for j in exp if j[1] in w.high_assurance]
            rest = [j for j in exp if j[1] not in w.high_assurance]
            before = s.snapshot(w) if ha and hasattr(s, "snapshot") else None
            if args.probe == "multi":
                import random
                pairs = multi_probes(w, exp, random.Random(w.seed))
                ha = [j for j in pairs if j[1] in w.high_assurance]
                rest = [j for j in pairs if j[1] not in w.high_assurance]
            for batch in (ha, rest):
                with ThreadPoolExecutor(6) as pool:
                    if args.probe == "multi":
                        for pair_rows in pool.map(lambda j: probe_pair(s, w, *j, args.k, exp), batch):
                            for row in pair_rows:
                                row["expected"] = exp[(row["agent"], row["location"], row["fact"])]
                                row["kind"] = oracle.probe_kind(w, row["agent"], row["location"], row["fact"])
                                rows.append(row)
                        continue
                    for (a, l, f), row in zip(batch, pool.map(lambda j: probe(s, w, *j, args.k, args.probe), batch)):
                        row["expected"] = exp[(a, l, f)]
                        row["kind"] = oracle.probe_kind(w, a, l, f)
                        rows.append(row)
                if batch is ha and before is not None:
                    after = s.snapshot(w)
                    changed = {b: {k: (before[b][k], after[b][k]) for k in before[b] if before[b][k] != after[b][k]}
                               for b in before if before[b] != after[b]}
                    audit.append({"system": s.name, "world": w.seed, "ha_probes": len(ha), "changed": changed})
                    print(f"side-effect audit {s.name} world {w.seed}: {len(ha)} high-assurance recalls, "
                          f"{'no change' if not changed else changed}", flush=True)
            print(f"probed {s.name} world {w.seed}: {len(exp)} probes", flush=True)
        for s in syss:
            if w.seed in getattr(s, "refused", {}):
                print(f"{s.name} refused {len(s.refused[w.seed])} carry-outs in world {w.seed}", flush=True)
    (out / "probes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    if audit:
        (out / "side_effects.json").write_text(json.dumps(audit, indent=1))
    summary = summarise(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "settings.json").write_text(json.dumps({"probe": args.probe, "banks_from": args.banks_from, "k": args.k,
                                                   "size": args.size, "seeds": args.seeds, "systems": args.systems}, indent=1))
    for system, groups in summary.items():
        o = groups["overall"]
        print(f"{system:9} leak {o['leaks']}/{o['must_not']} ({o['leak_rate']:.1%})  recall@20 {o['hits']}/{o['should']} ({o['recall']:.1%})  recall@5 {o['recall_at_5']:.1%}")
        for key, g in groups.items():
            if key != "overall":
                lr = f"{g['leak_rate']:.1%}" if g["leak_rate"] is not None else "  -  "
                rc = f"{g['recall']:.1%}" if g["recall"] is not None else "  -  "
                r5 = f"{g['recall_at_5']:.1%}" if g["recall_at_5"] is not None else "  -  "
                print(f"    {key:28} leak {lr:>6} ({g['leaks']}/{g['must_not']})   recall@20 {rc:>6} ({g['hits']}/{g['should']})  @5 {r5:>6}")


if __name__ == "__main__":
    main()
