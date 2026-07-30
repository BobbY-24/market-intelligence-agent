#!/usr/bin/env bash
set -euo pipefail

python3 -m agent_bias_arena.cli run --config configs/mvp.yaml "$@"
