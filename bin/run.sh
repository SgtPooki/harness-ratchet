#!/bin/bash
# Thin transitional wrapper over `ratchet baseline sweep` (issue #2, point 5:
# run.sh -> runner/omp.py). Same contract as the bash-era runner:
#   bin/run.sh <task-name|all|held-in|full> [model] [run-label] [k]
# Env passthrough: K, TIMEOUT_S, EXTRA_CONFIG (candidate --config overlay),
# EXTRA_SYS (trust-header-wrapped --append-system-prompt text).
# Note: ratchet.example.toml lists BOTH standing overlays (eval-isolation +
# the promoted ctxslim-v1), matching the era registry; the bash runner
# hardcoded only eval-isolation and rode ctxslim on EXTRA_CONFIG. Passing
# EXTRA_CONFIG=mutations/ctxslim-v1.yml here therefore double-applies a
# no-op overlay, which omp merges harmlessly.
set -u
cd "$(dirname "$0")/.."

TARGET="${1:?task|all|held-in|full}"
MODEL="${2:-vllm/homelab-default}"
LABEL="${3:-$(date +%Y%m%d-%H%M%S)}"
K="${4:-${K:-1}}"

case "$TARGET" in
  all|full) TASKS=(all) ;;
  held-in)  TASKS=($(python3 -c "import json; print('\n'.join(json.load(open('split.json'))['held_in']))")) ;;
  *)        TASKS=("$TARGET") ;;
esac

args=(baseline sweep "$LABEL" --config ratchet.example.toml
      --tasks "${TASKS[@]}" --k "$K" --model "$MODEL")
[ -n "${TIMEOUT_S:-}" ] && args+=(--timeout-s "$TIMEOUT_S")
[ -n "${EXTRA_CONFIG:-}" ] && args+=(--extra-config "$EXTRA_CONFIG")
[ -n "${EXTRA_SYS:-}" ] && args+=(--extra-sys "$EXTRA_SYS")

if command -v ratchet >/dev/null 2>&1; then
  exec ratchet "${args[@]}"
elif command -v uv >/dev/null 2>&1; then
  exec uv run --project . ratchet "${args[@]}"
else
  exec python3 -m ratchet.cli "${args[@]}"
fi
