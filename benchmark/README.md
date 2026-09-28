# smbench

Benchmarks for **selective agent memory**: memory where the agent's context (who it is, where it is, who it was with) decides what it may recall. The design lives in the project vault (`docs/vault/Concepts/Benchmark Plan.md`). This folder is self-contained so it can be split into its own repository at publication (`git subtree split --prefix=benchmark`). `smbench` is a working name.

## Status

| Part | State |
| --- | --- |
| ALCF gateway (6-request cap, token, retries, request log) | built, tested against a fake upstream |
| Memory-system adapters (Hindsight, Mem0, Falda; AgentCore reference) | not started |
| Selective-memory world generator and Cedar oracle | not started |
| Efficacy runs (LoCoMo, LongMemEval) | not started |

## ALCF gateway

All LLM traffic from memory systems, scripts and judges goes through one local gateway, so the shared ALCF endpoint never sees more than **6 concurrent requests** from us.

```sh
uv sync
uv run smbench-alcf-auth authenticate      # once; Globus login (token cached for 6 months of use)
uv run smbench-gateway                     # http://127.0.0.1:8411/v1
```

Point any OpenAI-compatible client at it (any API key works):

```sh
export OPENAI_BASE_URL=http://127.0.0.1:8411/v1
export OPENAI_API_KEY=gateway
```

| Model | Role | ALCF cluster |
| --- | --- | --- |
| `openai/gpt-oss-120b` | extraction and answering | Sophia (vLLM) |
| `nemotron-3-ultra` | judge | Minerva |
| `nvidia/nemotron-3-super-120b` | judge fallback | Sophia (vLLM) |
| `openai/gpt-oss-20b` | cheap tests | Sophia (vLLM) |

Send `X-Run-Id` and `X-System` headers to label requests. Each request is logged as a JSON line in `results/gateway/requests.jsonl`. `GET /health` shows requests in flight, requests queued, and totals.

## Tests

```sh
uv run pytest
```

The tests use a fake upstream and never call ALCF.

## Data

Datasets are downloaded by script, never committed. Raw results live in `results/` (gitignored).

## Licence

To be decided before publication. `src/smbench/alcf/auth.py` is vendored from [argonne-lcf/inference-endpoints](https://github.com/argonne-lcf/inference-endpoints) (MIT).
