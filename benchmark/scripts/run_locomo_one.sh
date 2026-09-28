#!/usr/bin/env bash
# One LoCoMo conversation for one system: scripts/run_locomo_one.sh <system> <prefix> <conversation>
set -uo pipefail
cd "$(dirname "$0")/.."
system=$1 prefix=$2 conv=$3
if .venvs/"$system"/bin/python -m smbench.locomo.run --system "$system" --run-id "$prefix-$system-$conv" \
     --conversations "$conv" --workers 3 > "results/logs/$prefix-$system-$conv.log" 2>&1; then
  echo "done $system $conv"
else
  echo "FAILED $system $conv (see results/logs/$prefix-$system-$conv.log)"
fi
