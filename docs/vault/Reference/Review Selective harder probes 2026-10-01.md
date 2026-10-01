---
type: review
status: active
authority: reference
summary: "The selective benchmark's stored worlds re-probed with harder questions (paraphrase, indirect) instead of the topic's own words. memgate still leaks 0 of 7,337 must-not probes. Paraphrases cost nothing. Indirect questions cost recall: on large worlds memgate falls to 95.6% at 20 and 71.6% at 5, but no filter falls further (73.4% and 47.2%) and per-agent stores too (80.3%, 58.5%): the filter removes the look-alikes a vague query pulls in, so selective memory recalls more, not less. Two-fact questions change nothing: a half-allowed question never pulls the forbidden half through memgate (0 of 310 mixed pairs), where no filter leaks it in 93%. Replicated on Mem0: memgate on Mem0 leaks 0 and recalls 94% at 5 under indirect questions where unfiltered Mem0 manages 47%."
created: 2026-10-01
updated: 2026-10-01
tags: [memgate, benchmark, selective-memory, results]
---

# Review: selective memory with harder probes, 2026-10-01

*Multi-fact results added the same day. The open item of every earlier selective review: direct probes ("What is the code for the kiln?") name the fact's own words, so recall sat at ceiling and the benchmark could not show a recall cost. This run re-probes the stored banks of [[Review Selective S4-S5 2026-09-29]] (env worlds 21–23) and [[Review Selective large 2026-09-29]] (large worlds 11, 12) with two harder question styles, written once per fact by gpt-oss-120b and saved in the released worlds (`benchmark/src/smbench/selective/questions.py`). Nothing was re-ingested: the same memories answer all three styles. Summary committed as benchmark/reports/selective-harder-2026-10-01.json; probe-level data in benchmark/results/selective/sel-*-{paraphrase,indirect}-*-2026-10-01/ (gitignored).*

**Result.** Paraphrased questions cost nothing; indirect ones cost recall, and the filter reduces the cost. memgate leaked **0 of 7,337** must-not probes across both sizes and all three styles. At 20, memgate recalls 100% on env worlds under every style and, on large worlds, 99.1% under direct and paraphrase and **95.6%** under indirect questions. The baselines fall much further under indirect questions: no filter to 73.4% at 20 on large worlds and per-agent stores to 80.3%. At 5 the gap widens (memgate 71.6%, per-agent 58.5%, no filter 47.2%). A vague query pulls in look-alike facts from other conversations; the filter removes the ones the agent may not see, and the baselines' top ranks fill with them. The "recall cost of selective memory" is therefore negative on these worlds: the same store recalls more of what the agent may know when it is forbidden the rest.

## The questions

- **paraphrase:** the same question in other words; it may still name the thing but not the topic phrase ("What is the access code for the laboratory safe?" for "the combination of the lab safe").
- **indirect:** no content word of the topic at all; refers to the fact the way the conversation did ("What was the code we noted earlier when we talked about checking that secure storage?").
- Neither may contain the code. A draft that breaks a rule is sent back to the model with the reason, up to eight times; all 95 facts in the five worlds got both questions. A probe still counts a hit by the exact code in the top 20, so leak rates remain judge-free.
- The indirect questions sometimes name who said it ("the code Dee mentioned"), which a witness would also say; they never name the thing.

## Env worlds (S4–S5: environments, carry-out, high assurance; 1,620 probes per system per style)

| Style | System | Leak rate | Recall at 20 | Recall at 5 |
| --- | --- | --- | --- | --- |
| direct | memgate | **0/1,446** | 174/174 | 100% |
| direct | no filter | 1,446/1,446 | 174/174 | 100% |
| direct | per-agent | 336/1,446 (23.2%) | 174/174 | 100% |
| paraphrase | memgate | **0/1,446** | 174/174 | 100% |
| paraphrase | no filter | 1,446/1,446 | 174/174 | 96.5% |
| paraphrase | per-agent | 336/1,446 (23.2%) | 174/174 | 97.1% |
| indirect | memgate | **0/1,446** | 174/174 | **89.1%** |
| indirect | no filter | 1,365/1,446 (94.4%) | 165/174 (94.8%) | 66.1% |
| indirect | per-agent | 336/1,446 (23.2%) | 174/174 | 81.6% |

By probe kind under indirect questions (memgate, recall at 5): witness-here 90%, carried fact 83%, carried opinion 83%, high-assurance witness inside the vault 100%, note in its own location 100%. The side-effect audit (recalls inside the vault bracketed by snapshots) reported no change in any run.

## Large worlds (S1–S3, 12 agents, 51 conversations with look-alike topics; 6,120 probes per system per style)

| Style | System | Leak rate | Recall at 20 | Recall at 5 |
| --- | --- | --- | --- | --- |
| direct | memgate | **0/5,891** | 227/229 (99.1%) | 99.1% |
| direct | no filter | 5,833/5,891 (99.0%) | 227/229 (99.1%) | 97.4% |
| direct | per-agent | 908/5,891 (15.4%) | 227/229 (99.1%) | 99.1% |
| paraphrase | memgate | **0/5,891** | 227/229 (99.1%) | 99.1% |
| paraphrase | no filter | 5,833/5,891 (99.0%) | 227/229 (99.1%) | 86.5% |
| paraphrase | per-agent | 908/5,891 (15.4%) | 227/229 (99.1%) | 98.7% |
| indirect | memgate | **0/5,891** | **219/229 (95.6%)** | **71.6%** |
| indirect | no filter | 4,332/5,891 (73.5%) | 168/229 (73.4%) | 47.2% |
| indirect | per-agent | 736/5,891 (12.5%) | 184/229 (80.3%) | 58.5% |

The two direct misses are the extraction losses noted in the large-world review; they recur under every style. Under indirect questions memgate's recall at 20 is 95.5% on witness-here probes and 100% (6/6) on retellings to a newcomer, where no filter manages 73.5% and 66.7%. The baselines' leak rates fall under indirect questions only because the leaked facts rank lower: a vague query retrieves fewer of the other conversations' codes into the top 20, not none. Wall time: about 47 min per style for the three systems (18,360 recalls).

## Multi-fact questions (two facts in one question)

A third style, run on the same banks: one question asking for two facts at once ("I need two things. First: <paraphrase of f1> Second: <paraphrase of f2>"), sampled per (agent, location) over three pair types: both facts recallable, one recallable and one not (**mixed**), and neither. Each fact in a pair is scored as its own probe. Env: 478 must-not and 284 should per system; large: 672 and 406.

| Size | System | Leak rate | Recall at 20 | Recall at 5 | Mixed pairs: leaks / recall at 5 |
| --- | --- | --- | --- | --- | --- |
| env | memgate | **0/478** | 284/284 | 98.9% | 0/118, 100% |
| env | no filter | 477/478 | 284/284 | 78.2% | 117/118, 86% |
| env | per-agent | 113/478 (23.6%) | 284/284 | 95.8% | 24/118, 100% |
| large | memgate | **0/672** | 404/406 (99.5%) | 96.1% | 0/192, 100% |
| large | no filter | 646/672 (96.1%) | 395/406 (97.3%) | 68.5% | 179/192, 81% |
| large | per-agent | 116/672 (17.3%) | 405/406 (99.8%) | 91.6% | 34/192, 98% |

The mixed pairs are the point: a question that is half allowed does not pull the forbidden half through. memgate answered the allowed fact in the top 5 every time and never retrieved the other; no filter retrieved the forbidden fact in 93% of mixed pairs. On both-should pairs, where two facts compete for five slots, memgate's recall at 5 is 92.5% on large worlds against 57% for no filter.


## The same worlds on Mem0

To check that the precision gain is not a Hindsight artefact, the env worlds were ingested into Mem0 (open source 2.2.0, in process, gpt-oss-120b extraction and bge-small embeddings through the same gateway) under the same three strategies (`systems_mem0.py`: one Mem0 scope per world, per agent, or per label set with memgate deciding), then probed with every style. 1,620 probes per system per style; multi 762.

| Style | mem0 + memgate | mem0, no filter | mem0, per agent |
| --- | --- | --- | --- |
| direct | **0/1,446** leaked; 100% at 20; 100% at 5 | 100% leaked; 100%; 100% | 23.2% leaked; 100%; 100% |
| paraphrase | **0/1,446**; 100%; 100% | 100%; 100%; 100% | 23.2%; 100%; 100% |
| indirect | **0/1,446**; 100%; **94.2%** | 96.7%; 93.1%; 47.1% | 23.2%; 100%; 77.0% |
| multi | **0/478**; 100%; 100% | 100%; 100%; 93.3% | 23.6%; 100%; 99.3% |

The same shape as on Hindsight, with a bigger gap at 5 under indirect questions (94% against 47%): Mem0's extraction writes one short fact per code, so the look-alikes that an unfiltered vague query pulls in compete more evenly. memgate's carry-out refusals and notes behaved identically (0 of 96 refused carry-outs retrievable, every note recalled in its own location only), with no second lock: Mem0 has no validator hook, so the client-side policy is the only enforcement, and scoping add() by label set is what keeps Mem0's own merges within one label set.

## Answer level, with indirect questions

The answer-level check (`leakcheck.py answers --probe indirect --sample 600`) re-asked a random 600 of memgate's must-not probes and 150 of its should probes from the 2026-09-29 runs (small, large and env worlds) with the indirect questions, requesting everything Hindsight's recall can return (memories, entity observations, raw chunks, source facts, trace), having gpt-oss-120b answer as the agent, and Nemotron 3 Ultra judge each must-not answer. Positive control: 100 of the per-agent stores' known leaks.

| | Must-not probes | Code anywhere in the response | Judge: VALUE | HINT | NONE | Answer recall (should probes) |
| --- | --- | --- | --- | --- | --- | --- |
| memgate | 600 | **0** | **0** | **0** | 600 | 79.3% (119/150) |
| per-agent (control) | 100 | 100 | 79 | 0 | 21 | |

Summary committed as benchmark/reports/selective-leakcheck-indirect-2026-10-01.json. The control shows the check still detects leaks under vague questions, though less often than under direct ones (79 against 98 VALUE of 100 on 2026-09-29): with a vague question the answering model more often declines even when the code is in front of it. memgate's answer-level recall fell from 99.2% (direct) to 79.3%, mostly on carried-out facts and opinions (20% to 29% of a small sample), where the indirect question refers back to a conversation the personal copy no longer mentions.

## Reading it

- **Indirect questions are the first probes that cost recall at 20,** and only on the large worlds with 51 look-alike conversations: memgate loses 3.5 points, the baselines 19 to 26. On env worlds (8 conversations) nothing is lost at 20. Paraphrases cost nobody anything at 20.
- **The filter is a precision gain, not a recall cost, on both stores.** Every memory the agent may recall is in the same store for all three systems; what differs is how many forbidden look-alikes compete for the top ranks. With them removed, memgate's top 5 holds the right fact 72% of the time on large worlds under indirect questions, against 47% for no filter. The expected trade-off (safety bought with recall) does not appear; the opposite does.
- **Recall is no longer at ceiling,** so later changes (a different extractor, a different store under memgate, larger worlds) can now move the number. The two extraction misses remain the floor for every system.
- **The baselines' lower leak rates under indirect questions are not safety.** Fewer codes reach the top 20 because retrieval is harder for everyone; the facts are still in reach. memgate's zero is structural.
- **Leaks are checked at answer level too.** The answer-level check ([[Selective Memory Benchmark]], `leakcheck.py`) found 0 VALUE or HINT disclosures in 3,312 memgate must-not probes with direct questions on 2026-09-29 and 0 in 600 with indirect questions here, with the code absent from every channel of every response.

## Next

- S6 (hierarchy) and S7 (scale), as before.
