---
type: review
status: active
authority: reference
summary: "The two checks before adopting Hindsight with memgate, both passed. Recall cost: LoCoMo with all ten conversations in one memgate bank scored 69.2% against 69.5% for isolated banks (paired p = 0.81); without the filter, 14% of questions pulled in other conversations' memories. Reworded leaks: 0 of 3,312 must-not probes disclosed anything at answer level (positive control 98/98 flagged), no code in any recall channel, and 0 lineage violations across 9 banks, including 1,840 consolidated observations in the shared LoCoMo bank."
created: 2026-09-29
updated: 2026-09-30
tags: [memgate, benchmark, results, decision-input]
---

# Review: memgate adoption checks, 2026-09-29

*The two checks named in the Decision Log row "Memory layer for Knowledge Ranch", after [[Review Selective S4-S5 2026-09-29]]. Reports: benchmark/reports/locomo-labels-2026-09-29.json and benchmark/reports/selective-leakcheck-2026-09-29.json. Code: `MemgateAdapter` ([[LoCoMo Harness]]) and leakcheck.py ([[Selective Memory Benchmark]]).*

**Result.** Both checks passed. Filtering costs no measurable recall on realistic conversations, and nothing leaks in reworded form, through consolidated memories, or through any other part of Hindsight's recall response.

## Check 1: the recall cost of filtering (LoCoMo, labels on vs off)

**Setup.** All ten LoCoMo conversations were stored through memgate in **one shared bank**. Each conversation took place at its own location between its two speakers. Each question was asked by the first speaker at that location, so memgate had to hide the other nine conversations and keep this one fully readable.

The comparison is the 2026-09-28 run, which gave each conversation its own bank ([[Review LoCoMo full 2026-09-28]]): the ideal isolation that filtering tries to match. A third condition searches the same shared bank with no filter. Everything else was the same in all three: Hindsight 0.10.1, recall budget "mid", k = 20, gpt-oss-120b answers, Nemotron 3 Ultra strict judge, 1,540 questions.

| | Isolated banks | Shared bank, memgate | Shared bank, no filter |
| --- | --- | --- | --- |
| **Overall** | 69.5% (67.1–71.7) | **69.2% (66.8–71.4)** | 68.4% (66.0–70.7) |
| Single-hop (841) | 75.7% | 74.6% | 72.9% |
| Multi-hop (282) | 49.6% | 48.6% | 48.9% |
| Temporal (321) | 74.5% | 77.3% | 77.9% |
| Open-domain (96) | 56.3% | 55.2% | 54.2% |
| Questions that pulled in another conversation's memories | 0 | **0** | 215 (14%) |
| Retrieved memories naming only another conversation's speakers | 0 | **0 of 30,800** | 612 (2.0%) |
| Search latency, median / p95 | 0.77 / 1.27 s | 0.68 / 1.06 s | |

- **No recall cost.** memgate against isolated banks: −0.3 points. Each got 141 and 136 questions right that the other missed (McNemar p = 0.81). Every category's interval overlaps, and per-conversation differences are within the run-to-run noise measured before (about 3 points on conv-26).
- **What the filter prevents.** Without it, 14% of questions pulled in other conversations' memories, for example the wrong John (three conversations have a speaker called John). Accuracy fell only 0.8 points (p = 0.32 against memgate), because LoCoMo questions name their speakers, so the right memories still ranked first. In a world where the same people meet in different places, that mixing is exactly the leak.
- **No latency cost.** memgate's recall was not slower. The runs were under different load, so this is "no cost", not "faster".
- **Loading time isn't comparable.** memgate loading was 23,208 s of summed process time, against 9,572 s. But each conversation's wait covered the whole shared bank, and the leak check was sharing the gateway at the time. This measures nothing about memgate's write overhead.

## Check 2: reworded leaks

### Lineage (exact, no LLM)

In every memgate bank:
- each memory unit must carry its source document's label set;
- each consolidated observation must carry the label set of every memory it was built from.

| Banks | Documents | Memory units | Observations (from sources) | Violations |
| --- | --- | --- | --- | --- |
| Selective, 8 banks (S1–S5, small, large, env) | 177 | 985 | 986 (from 1,001) | **0** |
| LoCoMo shared bank | 272 | 2,516 | 1,840 (from 2,511) | **0** |

The selective banks consolidated little (observations about 1:1 with facts). The LoCoMo bank is the real test: many observations merge several memories, across ten conversations with overlapping names, and none crosses a label set.

This matches Hindsight's design. Consolidation scopes each observation to its source's exact tag set (`all_strict`), so it only ever merges within one label set. That is the Decision Log rule "no merges across label sets", and here it is enforced by the store and verified by the audit.

### Answer level

**Setup.** memgate must-not probes were re-asked as the probing agent:
- every probe from the small and env worlds;
- every probe from the large worlds except non-witness, of which a sample of 500 was taken;
- 3,312 in all.

Each recall requested everything Hindsight can return: entity observations, raw chunks, source facts and the trace. Then:
1. the whole response was scanned for the code;
2. gpt-oss-120b answered from all of it, as the agent;
3. Nemotron 3 Ultra judged whether the answer disclosed the secret:
   - VALUE: the secret itself, or any part of it;
   - HINT: who, when or where, or that it came up at all;
   - NONE: nothing.

**Positive control.** 100 known leaks from the per-agent stores.

| | memgate | Control (per-agent leaks) |
| --- | --- | --- |
| Must-not probes | 3,312 | 100 |
| Code anywhere in the recall response | **0** | 100 |
| Judge: VALUE / HINT / NONE | **0 / 0 / 3,312** | 98 / 0 / 2 |
| Answer-level recall (should-probes) | 465/469 (99.1%) | – |

- **The detector works.** It flagged every control answer that disclosed the secret. In the 2 controls it labelled NONE, the answering model had picked a look-alike fact's code, so the secret really wasn't disclosed.
- **memgate: no reworded leaks, no hints, and nothing in the side channels** (entity observations, chunks, source facts, trace). The agent got about 20 pieces of memory per probe, none about the locked fact.
- **All 4 answer-level misses are answering errors, not filtering.** The code was in the recall response each time:
  - a typo ("HARBAR");
  - a look-alike confusion;
  - a carried opinion answered "I don't know". That probe was asked twice, so it counts as two misses.

## Reading it

- **The case for adopting Hindsight with memgate holds.** S1–S5 showed the rules hold at retrieval level. These checks add three things:
  - no recall cost on realistic, hard questions;
  - no reworded leak at answer level;
  - no path through derived memory.
- **The shared bank is the realistic deployment.** In the Ranch, agents share places and names across many conversations. Without the filter, one question in seven drew on conversations the agent wasn't part of.

## Limits

- **One run per condition.** The recall comparison rests on paired questions and on noise measured earlier on one conversation, not on repeated full runs.
- **Consolidation only.** The lineage audit covers observations. Mental models and reflect are blocked by the validator, so they weren't exercised.
- **Cooperative agents only.** Probes ask directly, matching the accepted threat model. An adversarial run was planned on 2026-09-30 and dropped: Claude's session couldn't build it, and writing it by hand wasn't worth the time then. Nothing here shows how memgate behaves against agents that try to extract locked memory or write around the rules. Before the Ranch runs agents that aren't trusted to cooperate, this needs doing: in-house, with red-team tooling (garak, PyRIT, promptfoo), or by an external review. Formal proofs of the Cedar policies (SymCC) and a trust-boundary review would narrow the gap without adversarial simulation.
- **Two leak-check limits:** probes still name the fact's topic, and the large worlds' non-witness probes were sampled (500 of 4,945).

## Open

- **Revocation of carry-outs.** Carried-out memories are relabelled as personal, so a later tightening of an environment's carry-out rule doesn't retract them. See the Decision Log. Collaborative Memory ([[Collaborative Memory]]) makes this retroactive by checking provenance at read time.
