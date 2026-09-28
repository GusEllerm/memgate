#!/usr/bin/env bash
# Run Hindsight (pinned in .venvs/hindsight) with every LLM call going through the local ALCF gateway.
set -euo pipefail
cd "$(dirname "$0")/.."
export HINDSIGHT_API_LLM_PROVIDER=openai
export HINDSIGHT_API_LLM_BASE_URL=${SMBENCH_GATEWAY:-http://127.0.0.1:8411/v1}
export HINDSIGHT_API_LLM_API_KEY=gateway
export HINDSIGHT_API_LLM_MODEL=${SMBENCH_MODEL:-openai/gpt-oss-120b}
export HINDSIGHT_API_LLM_MAX_CONCURRENT=6          # the gateway enforces 6 overall anyway
export HINDSIGHT_API_LLM_TIMEOUT=300
export HINDSIGHT_API_EMBEDDINGS_PROVIDER=local
export HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL=BAAI/bge-small-en-v1.5
export HINDSIGHT_API_LLM_TRACE_ENABLED=false       # default on; not needed for benchmarks
export HINDSIGHT_API_OTEL_TRACES_ENABLED=false
export HINDSIGHT_API_PORT=${HINDSIGHT_PORT:-8888}
exec .venvs/hindsight/bin/hindsight-api
