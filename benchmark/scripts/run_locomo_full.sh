#!/usr/bin/env bash
# Full LoCoMo for one memory system: one process per conversation, N at a time.
# Each process has its own run id (<prefix>-<system>-<conv>), so nothing is shared between them;
# the ALCF gateway still caps all of them together at 6 concurrent requests.
#
#   scripts/run_locomo_full.sh hindsight full-2026-09-28 3
set -euo pipefail
cd "$(dirname "$0")/.."
system=$1 prefix=$2 parallel=${3:-3}
mkdir -p results/logs
.venvs/"$system"/bin/python -c "from smbench.locomo import data; print('\n'.join(s['sample_id'] for s in data.load()))" |
  xargs -P "$parallel" -n 1 scripts/run_locomo_one.sh "$system" "$prefix"
