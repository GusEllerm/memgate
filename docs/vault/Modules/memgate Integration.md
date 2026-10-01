---
type: module
status: active
authority: describes
summary: "How memgate is packaged for an agent to integrate into a host (e.g. Knowledge Ranch): the Context-based API, the memgate command line (serve, check-world, conformance, secret), the integration guide, the integrate-memgate skill in the repo's Claude Code plugin, a runnable quickstart, and release 0.2.0."
created: 2026-09-30
updated: 2026-09-30
tags: [module, memgate, integration, knowledge-ranch]
---

# memgate Integration

> [!abstract] Role
> Everything an integrating agent needs, shipped with memgate. That agent works in the host's repo, without this vault or its history. Decided 2026-09-30: a Claude Code plugin with a skill, plus a plain guide; the library, with a `Context` seam and no service ([[Decision Log]]). The trust model it hands over is in [[Trust Boundaries]].

## Pieces

- **The guide:** `memgate/INTEGRATION.md`. It covers:
  - the rules;
  - the host contract (seven obligations, from verified context to labelled logs);
  - the world-file format;
  - install and run;
  - the API and when to call what;
  - verification;
  - what not to do without the owner;
  - the limits.

  A copy is bundled in the skill; `memgate/tests/test_docs.py` fails if the two differ.
- **The skill:** `plugins/memgate/skills/integrate-memgate/SKILL.md`, in the plugin `plugins/memgate`, listed by the repo's marketplace file `.claude-plugin/marketplace.json`. Install it with `claude plugin marketplace add GusEllerm/memgate` and `claude plugin install memgate@memgate`. Its procedure:
  1. survey the host;
  2. put the owner's decisions to the owner (high assurance, carry-out rules, identity, provenance, LLM);
  3. generate the world file from the host's model;
  4. deploy;
  5. put one memory module in the host that builds every Context;
  6. carry out the host's side of the contract;
  7. verify (conformance with 0 failures, plus host tests);
  8. report.
- **The API seam:** `Context` (agent, location, participants) in `memgate/src/memgate/context.py`. Every `HindsightMemory` call takes one ([[memgate Hindsight Adapter]]). The host builds it from verified facts, and that is where identity and context verification will plug in at integration.
- **The command line:** `memgate/src/memgate/cli.py`, installed as `memgate`:
  - `memgate serve` (`cmd_serve`): Hindsight with the validator. It checks the world file first, binds loopback unless `--allow-remote` is passed, turns off LLM traces, and takes LLM settings from `MEMGATE_LLM_*`. The database URL it prints is redacted by `redact_db_url`, and a URL with a password in its query is refused, because Hindsight 0.10.1 logs the query in clear. Both date from 0.3.1: 0.2.0 printed the URL in full, a leak found by the CHORUS integration. `memgate/tests/test_serve_logs.py` checks end to end that the password never reaches memgate's or Hindsight's output. Since 0.3.2 it also starts Hindsight in a private working directory with an empty `.env`, and the validator checks a fingerprint of what `serve` forced (`serve_fingerprint`). Hindsight would otherwise apply any `.env` found above its working directory over memgate's settings, a bypass found by the CHORUS review; `memgate/tests/test_serve_logs.py` shows a hostile `.env` can't disable the validator. `memgate/scripts/serve_hindsight_gated.sh` is now a wrapper over it, keeping this repo's defaults.
  - `memgate check-world` (`check_world` in `memgate/src/memgate/worldcheck.py`): the world-file format, with every mistake reported. The ids `--ha--` are reserved.
  - `memgate conformance` (`run` in `memgate/src/memgate/conformance.py`): canaries in a throwaway bank on the live deployment, 15 checks (`split-scope` only with `--partition-url`), adapting to the host's world. Checks the world has no place for are skipped. The bank is deleted afterwards, and the exit code is non-zero on any failure.
  - `memgate secret`: a new shared secret.
  - `memgate serve --socket` (since 0.4.0): serve on a Unix socket in a private directory instead of a port, the recommended deployment; clients and conformance take `unix:<path>`.
- **Example:** `memgate/examples/quickstart.py` with `memgate/examples/world.json`.
- **Release:** 0.4.0 (`memgate/CHANGELOG.md`): the Unix-socket transport, and no proxies. 0.3.1 and 0.3.2 are security patches for the printed database URL and the `.env` bypass. All of these came from CHORUS's review rounds. 0.3.0 was made for the Knowledge Ranch plan (decision D15 in CHORUS's `docs/knowledge-ranch/design/memory.md`, drafted with the chorus-dev session). The server installs `memgate[hindsight]`, which pins Hindsight 0.10.1. The host installs the client alone, with `memgate[async]` for `AsyncHindsightMemory`. 0.3.0 added:
  - `carry_out(source=<Recalled>)`;
  - the async client;
  - a separate partition server (`partition_url`, and `memgate serve --scope`);
  - the world check interval (`MEMGATE_WORLD_CHECK_S`, `memgate serve --world-check-interval`);
  - conformance on a split deployment (`--partition-url`, the `split-scope` check).

## Evidence (2026-09-30)

- **Conformance on this repo's deployment:** 14 of 14 passed. On a split deployment (shared and partition servers, 0.3.0): 15 of 15, including `split-scope`. It also runs as a live test (`test_conformance_passes_on_this_deployment`).
- **Negative control:** against a Hindsight without memgate's validator, the 6 checks that depend on the validator failed (secret, side doors, forged tags, write rules, partition search, seal) and the exit code was 1. The client-side checks still passed, so conformance tells the two locks apart.
- **Quickstart:** run against a fresh `memgate serve`, it refused both forbidden carry-outs, and recalled only what each context may read.
- **Plugin:** the plugin and marketplace manifests pass `claude plugin validate`.
