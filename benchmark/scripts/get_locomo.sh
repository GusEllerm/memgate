#!/usr/bin/env bash
# Download LoCoMo (snap-research/locomo, CC BY-NC 4.0) into data/locomo/ and check its hash.
# The dataset is never committed; see its licence before redistributing anything derived from it.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/locomo
curl -sSL -o data/locomo/locomo10.json https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json
echo "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4  data/locomo/locomo10.json" | shasum -a 256 -c -
