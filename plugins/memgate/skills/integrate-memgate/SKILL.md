---
name: integrate-memgate
description: Integrate memgate (context-scoped permissions for agent memory, in front of Hindsight) into a host application such as Knowledge Ranch. It maps the host's world to a memgate world file, deploys memgate serve, routes every memory call through a host-built Context, carries out the host's side of the contract, and verifies with memgate conformance. Use when asked to add memgate or permissioned, context-locked agent memory to a project.
---

# Integrate memgate into a host application

You are wiring memgate into a host that runs agents. memgate decides what each agent may recall, store and carry out from its context: who is acting, where, and who is present. It enforces that inside the memory store too. **It trusts the context it is given.** Most of your work is making sure the host gives it the truth, and closing the channels memgate can't see.

Before you change anything, read `INTEGRATION.md` in this skill's folder in full. It is the contract, the world-file format and the API. The steps below are the procedure. Keep a short integration log as you go; you will report from it at the end.

## 1. Survey the host (read only)

Find and note:
- **Agents:** how agents are identified, and how they run (in-process calls, or separate processes; their tools and network access).
- **Places:** where the host models locations or rooms, and any grouping of them. Groupings become environments.
- **Presence:** how the host knows where each agent is and who is with it, at the moment of each action. This is the source of truth for every `Context`.
- **Memory:** how agents store and recall memory today, if at all, and every place that would call memgate.
- **Agents' communication:** how an agent reaches the host (an API, a queue, tool calls). That path is where the host must verify the agent's identity.

Write a mapping in the log:

| Host concept | memgate concept |
| --- | --- |
| each place | a location |
| each grouping | an environment |
| each agent | an agent id |

Also list every host event that should trigger a memgate call (see "A turn" in the guide).

## 2. Decisions that belong to the owner

Do not guess these. Ask the owner, give a recommendation, and record the answers in the log:
- which locations are **high assurance**;
- each environment's **carry-out rule** (which of fact, opinion, skill, episode may leave; `[]` for none);
- **how agent identity is verified** and how the host vouches for location and participants. For separate agent processes this is required (see the contract, item 1). If the owner defers it, record that the deployment is only safe with cooperative agents;
- whether **provenance** is on, and where its files live;
- the **LLM endpoint and model** Hindsight will extract memories with, and where the secret and database live.

## 3. World file

- Add host code that generates the world file from the host's own model, so it can't drift. Write it atomically (temporary file, then rename). Regenerate it whenever agents, places or rules change; memgate reloads within a second.
- Run `memgate check-world <file>` and fix every error.

## 4. Deploy

- Install the pinned release named in `INTEGRATION.md`'s install lines (v0.4.4 at the time of writing; pin by tag or by commit hash), as two installs:
  - the server, in its own environment: `pip install "memgate[hindsight] @ git+https://github.com/GusEllerm/memgate@v0.4.4#subdirectory=memgate"`;
  - the client, in the host: the same URL without `[hindsight]`, with `[async]` if the host is asyncio (`AsyncHindsightMemory`), otherwise use the sync client in `asyncio.to_thread`.
- If high-assurance locations should be isolated on their own server, run a second `memgate serve --scope partitions` beside one with `--scope shared`, and pass `partition_url=` to the client. See the guide.
- Generate the secret with `memgate secret` and store it where only the host can read it. Never put it where an agent process can see it.
- Run `memgate serve` under the host's process supervision, with the owner's LLM settings, on a Unix socket in a private directory (`--socket <0700 dir>/memgate.sock`, address `unix:<path>`), so no other process can pose as the server and collect the secret. Use a loopback port only if a socket is impossible. Run the host and the server as the same user. The host process and the server must share `MEMGATE_WORLD`, `MEMGATE_REGISTRY` and `MEMGATE_SECRET`.

## 5. One memory module in the host

- **One module owns memgate.** It holds the `Gate` and `HindsightMemory`, and exposes host-level operations (recall for an agent, record a turn, take something along). Agents reach it only through the host's own interface.
- **It builds every `Context` itself,** from the verified caller identity and the host's presence state. Never pass through agent-supplied agent, location or participants. If the verification mechanism is deferred, put a single clearly named function at that seam, and mark it with the owner's decision.
- **Wire the lifecycle:**
  1. before an agent acts: `recall`;
  2. after it speaks: `say` (with the batch's `recall_id`), then `remember` (with `turns`);
  3. private notes: `keep_note`;
  4. leaving a location: `recall` there, let the agent pick what to take and classify each item (fact, opinion, skill, episode), then `carry_out(ctx, text, type, source=item)` per item. The recalled item is the source, because it may have formed with different people present. Then the host clears the agent's working context.
- **Handle errors.** A `PermissionError` is a refusal: tell the agent, don't retry around it. A `HindsightError` is a store failure: fail the action. Never continue without memory filtering.

## 6. The host's side of the contract

Implement each item, or record it in the log as an explicit open item the owner has signed off:
- Clear or seal an agent's working context when it leaves a location, always when it leaves a high-assurance one.
- Scope tools by location: storage the agent writes gets that location's labels; outbound tools are off inside high-assurance locations.
- Keep logs, traces and transcripts per high-assurance partition.
- Keep the secret and the store's port out of agents' reach (process separation, file permissions, network).

## 7. Verify

- `memgate check-world <file>` passes.
- `memgate conformance --url <server>` with the deployment's `MEMGATE_*` settings reports **0 failed**. Keep its output for the report. A skipped check means the world has no place to test that rule; note which.
- Add host tests:
  - a moving agent's Context follows it;
  - participants match who is present;
  - agent processes cannot read the secret or reach the store;
  - working context is cleared on leaving a high-assurance location.
- Run the host's own test suite.

## 8. Report to the owner

Cover:
- the mapping and the owner's decisions;
- what was built, and where;
- the conformance output;
- the host tests added;
- every open item from step 6 or the identity decision, marked with the risk it leaves.

## Stop and ask before

- changing memgate's Cedar policies, validator or any memgate source (upgrade by version instead);
- constructing a `Context` from anything an agent supplies;
- exposing the secret or the memory store to agents or the network;
- enabling Hindsight reflect or mental models;
- skipping or weakening a failing conformance check.
