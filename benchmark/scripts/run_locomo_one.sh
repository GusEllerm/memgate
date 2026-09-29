#!/usr/bin/env bash
# One LoCoMo conversation for one system: scripts/run_locomo_one.sh <system> <prefix> <conversation>
# Extra run.py flags via SMBENCH_EXTRA_ARGS, e.g. SMBENCH_EXTRA_ARGS=--skip-ingest (questions only).
# SMBENCH_VENV picks the environment when it isn't named after the system (memgate runs in hindsight's).
set -uo pipefail
cd "$(dirname "$0")/.."
system=$1 prefix=$2 conv=$3
venv=${SMBENCH_VENV:-$system}
if .venvs/"$venv"/bin/python -m smbench.locomo.run --system "$system" --run-id "$prefix-$system-$conv" \
     --conversations "$conv" --workers 3 ${SMBENCH_EXTRA_ARGS:-} > "results/logs/$prefix-$system-$conv.log" 2>&1; then
  echo "done $system $conv"
else
  echo "FAILED $system $conv (see results/logs/$prefix-$system-$conv.log)"
fi
