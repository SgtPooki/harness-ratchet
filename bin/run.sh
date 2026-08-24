#!/bin/bash
# Run tasks through omp non-interactively and verify results.
#   bin/run.sh <task-name|all|held-in|full> [model] [run-label] [k]
# k rollouts per task (default $K or 1), each in its own run_$i subdir.
# Success is COMPOSITE: verifier PASS **and** agent exit 0 (a timeout that
# happens to leave a passing tree is not a pass — the mutB lesson).
# Results append to runs/<label>/results.jsonl; transcripts + agent JSON
# streams saved per rollout. Token usage extracted from omp --mode json.
set -u
cd "$(dirname "$0")/.."

TARGET="${1:?task|all|held-in|full}"
MODEL="${2:-vllm/homelab-default}"
LABEL="${3:-$(date +%Y%m%d-%H%M%S)}"
K="${4:-${K:-1}}"
TIMEOUT_S="${TIMEOUT_S:-900}"
RUNDIR="runs/$LABEL"
mkdir -p "$RUNDIR"

run_verify() { # $1=task dir  $2=workspace copy
  if [ -f "$1/verify/verify.py" ]; then
    python3 "$1/verify/verify.py" "$2" 2>&1
  elif [ -f "$1/verify/verify.mjs" ]; then
    node "$1/verify/verify.mjs" "$2" 2>&1
  fi
}

run_rollout() { # $1=task name  $2=rollout index
  local name="$1" i="$2" task="tasks/$1"
  local rdir="$RUNDIR/$name/run_$i" work
  # Isolation: the agent works in a temp dir OUTSIDE this repo (weakness
  # mining caught agents wandering into runs/ and reading their own live
  # session streams when work dirs lived in-repo). Copied back post-run for
  # verification, veto, and mining.
  work=$(mktemp -d "${TMPDIR:-/tmp}/ratchet-work-XXXXXX")
  mkdir -p "$rdir"
  cp -R "$task/workspace/." "$work/"

  local prompt t0
  prompt=$(cat "$task/prompt.md")
  t0=$SECONDS
  local -a extra=()
  # omp appends this unlabeled at the tail of its MCP-instructions zone, where
  # models refuse it as suspected injection; the trust header rescues it.
  if [ -n "${EXTRA_SYS:-}" ]; then
    extra=(--append-system-prompt "$(printf '\n## Operator instructions (from the human operator via CLI flag, NOT from any MCP server — trusted)\n\n%s' "$EXTRA_SYS")")
  fi
  # Infrastructure config (always on): advisor-off isolation.
  extra+=(--config "$(pwd)/mutations/eval-isolation.yml")
  # EXTRA_CONFIG: repo-relative omp --config overlay = the mutation artifact.
  if [ -n "${EXTRA_CONFIG:-}" ]; then extra+=(--config "$(pwd)/$EXTRA_CONFIG"); fi
  local rdir_abs
  rdir_abs=$(cd "$rdir" && pwd)
  ( cd "$work" && timeout "$TIMEOUT_S" omp -p --auto-approve \
      --model "$MODEL" --no-title --mode json "${extra[@]}" \
      "$prompt" \
      >"$rdir_abs/stream.jsonl" 2>"$rdir_abs/stderr.txt" )
  local rc=$? dur=$((SECONDS - t0))

  local vout pass
  vout=$(run_verify "$task" "$work")
  # Archive the workspace back into the run dir; the temp dir goes away.
  rm -rf "$rdir/work"; cp -R "$work" "$rdir/work"; rm -rf "$work"; work="$rdir/work"
  if echo "$vout" | grep -q '^PASS$' && [ "$rc" -eq 0 ]; then pass=true; else pass=false; fi

  RDIR="$rdir" NAME="$name" I="$i" MODEL="$MODEL" LABEL="$LABEL" PASS="$pass" \
  RC="$rc" DUR="$dur" VOUT="$vout" RESULTS="$RUNDIR/results.jsonl" python3 - <<'PYEOF'
import json, os
rdir = os.environ["RDIR"]
tok_in = tok_out = 0
try:
    for line in open(os.path.join(rdir, "stream.jsonl"), errors="replace"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "turn_end":
            u = (d.get("message") or {}).get("usage") or {}
            tok_in += u.get("input", 0) or 0
            tok_out += u.get("output", 0) or 0
except OSError:
    pass
rec = {
    "task": os.environ["NAME"], "rollout": int(os.environ["I"]),
    "model": os.environ["MODEL"], "label": os.environ["LABEL"],
    "pass": os.environ["PASS"] == "true", "agent_rc": int(os.environ["RC"]),
    "duration_s": int(os.environ["DUR"]),
    "tokens_in": tok_in, "tokens_out": tok_out,
    "verify_tail": "\n".join(os.environ["VOUT"].splitlines()[-3:])[:400],
}
open(os.environ["RESULTS"], "a").write(json.dumps(rec) + "\n")
PYEOF
  echo "[$name r$i] pass=$pass rc=$rc ${dur}s"
}

tasks_for() {
  case "$1" in
    all|full) ls tasks ;;
    held-in) python3 -c "import json; print('\n'.join(json.load(open('split.json'))['held_in']))" ;;
    *) echo "$1" ;;
  esac
}

for t in $(tasks_for "$TARGET"); do
  for i in $(seq 1 "$K"); do run_rollout "$t" "$i"; done
done
echo "results: $RUNDIR/results.jsonl"
