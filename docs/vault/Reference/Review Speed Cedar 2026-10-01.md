---
type: review
status: active
authority: reference
summary: "First speed run of memgate's decisions, no LLM (plan §3): a compiled read decision costs 1.6 ms at 1k label sets, 11 ms at 10k, 178 ms at 100k and 2.5 s at 1M (cold, once per agent-location pair), then under 0.2 ms warm. The compiled filter agreed with Cedar's exact answer at every size it could run (up to 100k, where exact takes 9.3 s). A write decision costs 0.5 to 5.7 ms, growing with the world, not the registry."
created: 2026-10-01
updated: 2026-10-01
tags: [memgate, benchmark, speed, results]
---

# Review: speed of memgate's decisions, 2026-10-01

*First run of plan §3's Cedar measurements ([[Benchmark Plan]]), with `benchmark/src/smbench/speed/cedar.py`. Summary committed as benchmark/reports/speed-cedar-2026-10-01.json; registries and raw timings in benchmark/results/speed/ (gitignored). Apple Silicon laptop (macOS 26.6, Python 3.12.11, cedarpy 4.12.1, memgate 0.4.2), 20 timed decisions per size, seed 1.*

**Result.** The cost of "which label sets may this agent read here?" is linear in the registry on first contact and flat afterwards. The compiler is verified at scale: at 1k, 10k and 100k label sets its answer equalled Cedar's exact answer on every ask.

## Setup

- One registry per size, holding 1k, 10k, 100k or 1M distinct label sets: 80% conversations (a location and 2 to 4 participants), 10% personal memory, 10% notes kept in a location.
- The world grows with the registry: 20 agents, 8 locations, 2 environments at 1k, up to 2,000 agents, 200 locations and 16 environments at 1M, with a quarter of locations high-assurance (so the seal's literal lists grow too).
- Four decisions timed, each for 20 random (agent, location) asks:
  - **cold** `Policy.allowed_ids`: a fresh `Policy`, so Cedar partial evaluation plus the compiled SQL filter over the whole registry;
  - **warm**: the same `Policy` asked again after 50 more label sets were registered (the incremental path);
  - **exact** `Policy.allowed_ids_exact`: one Cedar request per registered label set, the reference answer, compared with the compiled one; skipped at 1M;
  - **write** `Policy.may_write`: one conversation write.

## Results (medians)

| Label sets | Agents / locations | Allowed per ask | Cold | Warm | Exact | Write | Registry |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 20 / 8 | 19 | 1.6 ms | 0.04 ms | 77 ms | 0.5 ms | 1 MB |
| 10,000 | 100 / 20 | 13 | 11 ms | 0.05 ms | 0.8 s | 0.8 ms | 6 MB |
| 100,000 | 500 / 60 | 9 | 178 ms | 0.08 ms | 9.3 s | 1.8 ms | 62 MB |
| 1,000,000 | 2,000 / 200 | 8 | 2.5 s | 0.19 ms | (skipped) | 5.7 ms | 635 MB |

p95 is within 5% of the median everywhere. Registering 1M label sets took 500 s (one commit per `register`).

## Reading it

- **Cold is a scan.** `EXPLAIN QUERY PLAN` at 1M: a full scan of `label_sets` with indexed correlated subqueries per row. The SQL compiled from Cedar's residual tests each label set in turn; nothing lets SQLite start from the principal's own labels. Hence the linear growth, and 2.5 s at a million.
- **It is paid once per (agent, location) per process.** `allowed_ids` caches the answer and afterwards checks only label sets registered since (`Registry.select_ids` by rowid), which is why warm stays under 0.2 ms even at 1M. A host that recalls for the same agents in the same places pays the cold cost at first contact only. The validator inside Hindsight has its own cache, so the server pays it once too.
- **The compiler is right at scale.** The exact check, 52× slower at 100k, agreed on 20 asks per size. The same policies, the same worlds.
- **Writes depend on the world, not the registry.** `may_write` rebuilds Cedar's entity set from the whole world on every call (`Policy._entities`), so it grows with agents and locations: 5.7 ms at 2,000 agents. Fine for a host; worth caching if worlds get large.
- **Scale in context.** The selective benchmark's large worlds register about 60 label sets; a Knowledge Ranch tree with a dozen agents registers one per distinct seated set. A million label sets is far beyond any current use; 100k (178 ms cold) is the realistic ceiling for a long-running deployment.

## Next

- **Driving the query from the principal's labels** (candidate label sets = those carrying `with:<agent>` or `self:<agent>`, then the compiled conditions) would make cold cost proportional to the agent's own label sets, not the registry. A memgate change, not a benchmark one; the exact check in this suite is the test for it.
- **Entity caching for `may_write`**, keyed on the world fingerprint.
- The rest of plan §3: filtered vector search inside Hindsight (tight and loose tag filters against exact search) and partition fan-out, both of which need a populated store.
