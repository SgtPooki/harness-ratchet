#!/bin/bash
# Interleaved 3-arm attribution experiment (peer-review consensus, 2026-08-24):
#   armA exp-v4       — current runner + ctxslim overlay (v4 config)
#   armB exp-noslim   — current runner, NO overlay (isolates ctxslim on v4 infra)
#   armC exp-v2replay — v2-era runner from git (in-repo workspaces, advisor ON,
#                       no overlay) — tests whether v2's numbers reproduce today
# Per task, arms run back-to-back with rotating order (kills time-of-day and
# server-state confounds at task granularity). k=2 each; original 8 tasks only
# (09 is not yet in the split).
set -u
cd "$(dirname "$0")/.."

TASKS=$(python3 -c "import json; s=json.load(open('split.json')); print(' '.join(sorted(s['held_in']+s['held_out']+s['sentinel'])))")

n=0
for t in $TASKS; do
  case $((n % 3)) in
    0) order="A B C" ;;
    1) order="B C A" ;;
    2) order="C A B" ;;
  esac
  for arm in $order; do
    case $arm in
      A) EXTRA_CONFIG=mutations/ctxslim-v1.yml bash bin/run.sh "$t" vllm/homelab-default exp-v4 2 ;;
      B) EXTRA_CONFIG= bash bin/run.sh "$t" vllm/homelab-default exp-noslim 2 ;;
      C) EXTRA_CONFIG= bash bin/run-v2era.sh "$t" vllm/homelab-default exp-v2replay 2 ;;
    esac
  done
  n=$((n + 1))
done
echo EXP_DONE
