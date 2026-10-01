"""Speed of memgate's decisions, with no LLM and no memory store (plan §3, "Cedar").

    uv run python -m smbench.speed.cedar --out results/speed/cedar-2026-10-01 [--sizes 1000 10000 100000 1000000]

What is measured, per registry size (number of distinct label sets):
- `allowed_ids` cold: a fresh Policy answers "which label sets may this agent read here?" (Cedar
  partial evaluation, the compiled SQL filter over the whole registry).
- `allowed_ids` warm: the same question again after a few more label sets were registered (the
  incremental path: only the new rows are checked).
- `allowed_ids_exact`: the reference answer, one Cedar request per label set, while it is affordable;
  checked equal to the compiled answer, so the compiler is verified at scale too.
- `may_write`: one write decision, which rebuilds the Cedar entity set from the whole world each time,
  so its cost depends on the world's size, not the registry's.

Worlds grow with the registry: more agents, more locations, more environments, a share of
high-assurance locations, so the compiled filter's literal lists (haLocs) grow too. Label sets are a
realistic mix: conversations (location + 2 to 4 participants), personal memory, and notes.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

from memgate.labels import LabelSet
from memgate.policy import Policy
from memgate.registry import Registry
from memgate.world import World

# registry size -> (agents, locations, environments)
SHAPES = {1_000: (20, 8, 2), 10_000: (100, 20, 4), 100_000: (500, 60, 8), 1_000_000: (2_000, 200, 16)}
HA_SHARE = 0.25          # high-assurance locations
REPEATS = 20             # decisions timed per size
TOP_UP = 50              # label sets registered between the cold and warm measurements
EXACT_LIMIT = 100_000    # allowed_ids_exact above this is skipped (Cedar batch of that many requests)


def build_world(n_agents: int, n_locs: int, n_envs: int, rng: random.Random) -> World:
    w = World()
    for e in range(n_envs):
        w.add_environment(f"env{e}", carry_out=rng.choice([("fact", "opinion", "skill", "episode"), ("opinion", "skill"), ()]))
    for l in range(n_locs):
        w.add_location(f"loc{l}", f"env{l % n_envs}", high_assurance=rng.random() < HA_SHARE)
    w.add_agents(*(f"agent{a}" for a in range(n_agents)))
    return w


def label_sets(world: World, n: int, rng: random.Random):
    """A realistic mix: 80% conversations, 10% personal, 10% notes; distinct by construction."""
    agents, locs = sorted(world.agents), sorted(world.locations)
    seen: set[str] = set()
    while len(seen) < n:
        r = rng.random()
        if r < 0.8:
            ls = LabelSet.build(locs=[rng.choice(locs)], withs=rng.sample(agents, rng.choice([2, 2, 3, 4])))
        elif r < 0.9:
            ls = LabelSet.build(selfs=[rng.choice(agents)])
        else:
            ls = LabelSet.build(selfs=[rng.choice(agents)], locs=[rng.choice(locs)])
        if ls.id not in seen:
            seen.add(ls.id)
            yield ls


def timed(fn, repeats: int) -> dict:
    samples = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t)
    samples.sort()
    return {"n": repeats, "median_ms": round(1000 * statistics.median(samples), 3),
            "p95_ms": round(1000 * samples[int(0.95 * (len(samples) - 1))], 3),
            "min_ms": round(1000 * samples[0], 3), "max_ms": round(1000 * samples[-1], 3)}


def measure(size: int, out_dir: Path, rng: random.Random) -> dict:
    n_agents, n_locs, n_envs = SHAPES[size]
    world = build_world(n_agents, n_locs, n_envs, rng)
    reg_path = out_dir / f"registry-{size}.sqlite"
    reg_path.unlink(missing_ok=True)
    reg = Registry(reg_path)
    t = time.perf_counter()
    for ls in label_sets(world, size, rng):
        reg.register(ls)
    register_s = time.perf_counter() - t
    print(f"[{size}] registered {len(reg)} label sets in {register_s:.1f}s "
          f"({n_agents} agents, {n_locs} locations, {n_envs} environments)", flush=True)

    agents, locs = sorted(world.agents), sorted(world.locations)
    asks = [(rng.choice(agents), rng.choice(locs)) for _ in range(REPEATS)]
    row: dict = {"size": size, "label_sets": len(reg), "agents": n_agents, "locations": n_locs, "environments": n_envs,
                 "high_assurance": sum(world.high_assurance(l) for l in locs), "register_s": round(register_s, 1),
                 "registry_bytes": reg_path.stat().st_size}

    # cold: a fresh Policy per ask (partial evaluation + the full compiled query)
    cold_sizes = []

    def cold(ask):
        allowed = Policy(world, reg).allowed_ids(*ask)
        cold_sizes.append(len(allowed))
    it = iter(asks)
    row["allowed_ids_cold"] = timed(lambda: cold(next(it)), REPEATS)
    row["allowed_mean"] = round(statistics.mean(cold_sizes), 1)

    # warm: one Policy, the same asks again after a top-up of new label sets (incremental path)
    pol = Policy(world, reg)
    for ask in asks:
        pol.allowed_ids(*ask)
    for ls in label_sets(world, TOP_UP, random.Random(size + 1)):
        reg.register(ls)
    it = iter(asks)
    row["allowed_ids_warm"] = timed(lambda: pol.allowed_ids(*next(it)), REPEATS)

    # exact: the reference answer, and the check that the compiler agrees
    if size <= EXACT_LIMIT:
        it = iter(asks)
        mismatches = 0

        def exact():
            ask = next(it)
            if pol.allowed_ids_exact(*ask) != pol.allowed_ids(*ask):
                nonlocal mismatches
                mismatches += 1
        n_exact = REPEATS if size <= 10_000 else 3
        row["allowed_ids_exact"] = timed(exact, n_exact)
        row["compiled_matches_exact"] = mismatches == 0
        print(f"[{size}] exact vs compiled: {'agree' if mismatches == 0 else f'{mismatches} MISMATCHES'}", flush=True)

    # may_write: a conversation write, entities rebuilt from the whole world each call
    it = iter(asks)

    def write():
        agent, loc = next(it)
        pol.may_write(agent, loc, LabelSet.build(locs=[loc], withs=[agent, rng.choice(agents)]))
    row["may_write"] = timed(write, REPEATS)
    return row


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True)
    p.add_argument("--sizes", type=int, nargs="+", default=sorted(SHAPES))
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    from importlib.metadata import version
    report = {"date": time.strftime("%Y-%m-%d"), "seed": args.seed, "repeats": REPEATS,
              "machine": {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0],
                          "cedarpy": version("cedarpy"), "memgate": version("memgate")},
              "sizes": []}
    for size in args.sizes:
        if size not in SHAPES:
            p.error(f"size must be one of {sorted(SHAPES)}")
        row = measure(size, out, random.Random(args.seed))
        report["sizes"].append(row)
        (out / "report.json").write_text(json.dumps(report, indent=1))
        print(f"[{size}] allowed_ids cold {row['allowed_ids_cold']['median_ms']} ms, warm {row['allowed_ids_warm']['median_ms']} ms"
              + (f", exact {row['allowed_ids_exact']['median_ms']} ms" if "allowed_ids_exact" in row else "")
              + f", may_write {row['may_write']['median_ms']} ms (medians; {row['allowed_mean']} label sets allowed on average)",
              flush=True)
    print(f"wrote {out / 'report.json'}")


if __name__ == "__main__":
    main()
