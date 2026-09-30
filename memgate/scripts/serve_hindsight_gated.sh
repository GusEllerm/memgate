#!/usr/bin/env bash
# Hindsight with memgate's validator loaded (the second lock), on its own port and database.
# A wrapper over `memgate serve` that keeps this repo's defaults (memgate/.run/, the ALCF gateway);
# integrators should call `memgate serve` directly (see INTEGRATION.md).
# Needs: memgate installed in the Hindsight environment (pip install 'memgate[hindsight]'), and
# MEMGATE_SECRET set. Overrides: MEMGATE_WORLD, MEMGATE_REGISTRY, HINDSIGHT_PORT, HINDSIGHT_DB,
# SMBENCH_GATEWAY, SMBENCH_MODEL, HINDSIGHT_BIN.
set -euo pipefail
cd "$(dirname "$0")/.."
RUN=${MEMGATE_RUN:-$PWD/.run}
export MEMGATE_WORLD=${MEMGATE_WORLD:-$RUN/world.json}
export MEMGATE_REGISTRY=${MEMGATE_REGISTRY:-$RUN/registry.sqlite}
export MEMGATE_SECRET=${MEMGATE_SECRET:?set MEMGATE_SECRET}
export MEMGATE_LLM_API_KEY=${MEMGATE_LLM_API_KEY:-gateway}
BIN=${HINDSIGHT_BIN:-../benchmark/.venvs/hindsight/bin/hindsight-api}
exec "$(dirname "$BIN")/memgate" serve --port "${HINDSIGHT_PORT:-8889}" --db "${HINDSIGHT_DB:-pg0://memgate}" \
  --llm-base-url "${SMBENCH_GATEWAY:-http://127.0.0.1:8411/v1}" --llm-model "${SMBENCH_MODEL:-openai/gpt-oss-120b}" \
  --hindsight-bin "$BIN"
