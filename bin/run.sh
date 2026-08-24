#!/bin/bash
# Run one task (or all) through omp non-interactively and verify the result.
#   bin/run.sh <task-name|all> [model] [run-label]
# Results append to runs/<label>/results.jsonl; full transcripts saved per task.
set -u
cd "$(dirname "$0")/.."

MODEL="${2:-vllm/homelab-default}"
LABEL="${3:-$(date +%Y%m%d-%H%M%S)}"
TIMEOUT_S=900
RUNDIR="runs/$LABEL"
mkdir -p "$RUNDIR"

run_verify() { # $1=task dir  $2=workspace copy
  if [ -f "$1/verify/verify.py" ]; then
    python3 "$1/verify/verify.py" "$2" 2>&1
  elif [ -f "$1/verify/verify.mjs" ]; then
    node "$1/verify/verify.mjs" "$2" 2>&1
  fi
}

run_task() {
  local task="tasks/$1" name="$1"
  local work="$RUNDIR/$name/work"
  mkdir -p "$RUNDIR/$name"
  rm -rf "$work"; cp -R "$task/workspace" "$work"

  local prompt t0
  prompt=$(cat "$task/prompt.md")
  t0=$SECONDS
  local -a extra=()
  if [ -n "${EXTRA_SYS:-}" ]; then extra=(--append-system-prompt "$EXTRA_SYS"); fi
  ( cd "$work" && timeout "$TIMEOUT_S" omp -p --auto-approve \
      --model "$MODEL" --no-title "${extra[@]}" \
      "$prompt" \
      >"../transcript.txt" 2>&1 )
  local rc=$? dur=$((SECONDS - t0))

  local vout pass
  vout=$(run_verify "$task" "$work")
  if echo "$vout" | grep -q '^PASS$'; then pass=true; else pass=false; fi

  python3 - "$RUNDIR/results.jsonl" <<PYEOF
import json, sys
rec = {"task": "$name", "model": "$MODEL", "label": "$LABEL",
       "pass": "$pass" == "true", "agent_rc": $rc, "duration_s": $dur,
       "verify_tail": """$(echo "$vout" | tail -3 | head -c 400 | sed 's/"/\\\\"/g')"""}
open(sys.argv[1], "a").write(json.dumps(rec) + "\n")
PYEOF
  echo "[$name] pass=$pass rc=$rc ${dur}s"
}

if [ "$1" = "all" ]; then
  for t in tasks/*/; do run_task "$(basename "$t")"; done
else
  run_task "$1"
fi
echo "results: $RUNDIR/results.jsonl"
