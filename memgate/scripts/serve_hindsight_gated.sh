#!/usr/bin/env bash
# Hindsight with memgate's validator loaded (the second lock), on its own port and database.
# Needs: memgate installed in the Hindsight environment, the ALCF gateway running, and
# MEMGATE_WORLD / MEMGATE_REGISTRY / MEMGATE_SECRET set (defaults under memgate/.run/).
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=${MEMGATE_RUN:-$PWD/.run}
export MEMGATE_WORLD=${MEMGATE_WORLD:-$RUN/world.json}
export MEMGATE_REGISTRY=${MEMGATE_REGISTRY:-$RUN/registry.sqlite}
export MEMGATE_SECRET=${MEMGATE_SECRET:?set MEMGATE_SECRET}
export HINDSIGHT_API_OPERATION_VALIDATOR_EXTENSION=memgate.adapters.hindsight.validator:MemgateValidator
export HINDSIGHT_API_EXTENSION_PASSTHROUGH_HEADERS=x-memgate-agent,x-memgate-location,x-memgate-secret,x-memgate-role
export HINDSIGHT_API_DATABASE_URL=${HINDSIGHT_DB:-pg0://memgate}
export HINDSIGHT_API_HOST=127.0.0.1                 # never expose the memory store beyond this machine
export HINDSIGHT_API_PORT=${HINDSIGHT_PORT:-8889}
export HINDSIGHT_API_LLM_PROVIDER=openai
export HINDSIGHT_API_LLM_BASE_URL=${SMBENCH_GATEWAY:-http://127.0.0.1:8411/v1}
export HINDSIGHT_API_LLM_API_KEY=gateway
export HINDSIGHT_API_LLM_MODEL=${SMBENCH_MODEL:-openai/gpt-oss-120b}
export HINDSIGHT_API_LLM_MAX_CONCURRENT=6
export HINDSIGHT_API_LLM_TIMEOUT=300
export HINDSIGHT_API_EMBEDDINGS_PROVIDER=local
export HINDSIGHT_API_EMBEDDINGS_LOCAL_MODEL=BAAI/bge-small-en-v1.5
export HINDSIGHT_API_LLM_TRACE_ENABLED=false
export HINDSIGHT_API_AUDIT_LOG_ENABLED=false
export HINDSIGHT_API_OTEL_TRACES_ENABLED=false
exec "${HINDSIGHT_BIN:-../benchmark/.venvs/hindsight/bin/hindsight-api}"
