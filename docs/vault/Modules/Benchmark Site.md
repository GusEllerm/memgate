---
type: module
status: active
authority: describes
summary: "The published benchmark record (a private claude.ai artifact) built from benchmark/site/registry.json and the run reports: systems, benchmarks, results with 95% intervals, published comparisons, protocol, runs and findings. Edit the registry, rebuild, republish to the same URL."
created: 2026-09-28
updated: 2026-09-28
tags: [module, benchmark, site]
---

# Benchmark Site

> [!abstract] Role
> One page that describes the benchmarking and its results. It grows as memory systems, benchmarks and runs are added.

**Published at:** https://claude.ai/artifact/4cAXRXWnBoiZGrsmfHkMNd (private; share from the page's Share menu).

Code:
- `benchmark/src/smbench/site/build.py` (`build`, `normalise`);
- the page template `benchmark/site/template.html`;
- the data `benchmark/site/registry.json`.

The built page, benchmark/site/build/smbench.html, is gitignored.

## How to update

1. **Edit `benchmark/site/registry.json`:**
   - a memory system goes in `systems`; its `slot` (1–4) fixes its chart colour;
   - a benchmark goes in `benchmarks`, with its categories;
   - a run goes in `runs`, pointing at its report JSON; `headline: true` puts it at the top of the page;
   - vendor or paper figures go in `published`;
   - dated lessons go in `findings`;
   - fixed settings go in `protocol`.
2. **Rebuild:** `uv run python -m smbench.site.build` (from benchmark/, in any env with smbench installed).
3. **Republish:**
   - **In the session that first published it:** republish the same file path.
   - **From any other session:** pass the URL above as `url`, which keeps the link.

## Report formats

`normalise` reads two formats:
- **`aggregate`:** the output of `benchmark/src/smbench/locomo/aggregate.py`.
- **`pilot`:** the early single-conversation report.

Category scores are matched to the benchmark's categories by name. A new benchmark whose report looks different needs a new format branch in `normalise`.

## Design

- **Results:** a dot at each accuracy with its 95% interval, per category and system, plus a table with the same numbers.
- **Colours:** each system keeps one colour across every chart. Hindsight, Mem0, Falda and AgentCore take slots 1–4, and the palette was validated for colour-blind separation in light and dark.
- **Accessibility:** aqua and yellow fall below 3:1 contrast on light, so every chart has a legend, labels and a table view.
- **Tooltips:** on every dot, reachable by keyboard.
