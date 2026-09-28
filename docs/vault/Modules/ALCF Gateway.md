---
type: module
status: active
authority: describes
summary: "Local OpenAI-compatible gateway that every benchmark component uses to reach the ALCF inference service: a hard cap of 6 concurrent upstream requests, model-to-cluster routing, Globus token refresh, retries with backoff, and a JSON-lines request log."
created: 2026-09-28
updated: 2026-09-28
tags: [module, benchmark, alcf]
---

# ALCF Gateway

> [!abstract] Role
> The one door to ALCF: it keeps us within the agreed 6 concurrent requests, and records what every run cost.

Code: `benchmark/src/smbench/alcf/gateway.py`, with auth vendored in `benchmark/src/smbench/alcf/auth.py`. Decisions in [[Decision Log]]; plan in [[Benchmark Plan]].

## What it does

- **Serves** `/v1/chat/completions`, `/v1/completions`, `/v1/responses` and `/v1/embeddings` on `http://127.0.0.1:8411/v1`, plus `/v1/models` (ALCF doesn't serve that route) and `/health`.
- **Caps concurrency.** Every upstream request holds one of `MAX_CONCURRENCY` (6) slots in a single semaphore. `create_app` refuses a higher setting, so the cap covers every memory system and script sharing the gateway.
- **Routes by model.** `ROUTES` maps each model to its cluster:
  - gpt-oss-120b, gpt-oss-20b and Nemotron 3 Super go to Sophia vLLM;
  - Nemotron 3 Ultra goes to Minerva.
  - An unknown model gets a 400 listing the known ones.
- **Handles the token.** `TokenCache` fetches a Globus access token through `get_access_token` and refreshes it after 60 s or on an upstream 401.
- **Retries** statuses in `RETRY_STATUSES` (502, 503, 504) and connection errors, up to 4 attempts with exponential backoff. It sleeps *outside* the semaphore, so a retrying request doesn't hold a slot.
- **Logs** one line per request via `RequestLog`: run ID and system (from the `X-Run-Id` and `X-System` headers), model, status, attempts, queue wait, upstream time, and prompt and completion tokens.

## How to run

`uv run smbench-alcf-auth authenticate` once; then `uv run smbench-gateway`. Clients set `OPENAI_BASE_URL=http://127.0.0.1:8411/v1` and any API key.

## Tests

`benchmark/tests/test_gateway.py` runs against a fake upstream with no ALCF traffic. It covers:
- 20 simultaneous requests never exceed 6 upstream;
- the cap cannot be raised, and lower caps are respected;
- 503 retries, and giving up after the attempt limit;
- token refresh on 401;
- unknown-model rejection;
- streaming pass-through.

**Live check, 2026-09-28:** one request each to gpt-oss-120b (2.8 s upstream) and Nemotron 3 Ultra (0.2 s) through the gateway, both answered and logged.
