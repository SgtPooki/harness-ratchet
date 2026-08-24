#!/bin/bash
# Sequenced experiment run:
#   1. Clean baseline of the new hard tasks (07, 08) — RULES.md untouched.
#   2. mutB: append a scope-control rule to ~/.omp/agent/RULES.md, re-run 04.
#   3. Restore RULES.md no matter what.
set -u
cd "$(dirname "$0")/.."

RULES="$HOME/.omp/agent/RULES.md"
BACKUP="$RULES.ab-backup"

restore() {
  if [ -f "$BACKUP" ]; then mv "$BACKUP" "$RULES"; echo "RULES.md restored"; fi
}
trap restore EXIT

# Phase 1: clean hard-task baseline
bash bin/run.sh 07-py-lru-ttl vllm/homelab-default baseline-qwen38-thinking
bash bin/run.sh 08-py-report-bleed vllm/homelab-default baseline-qwen38-thinking

# Phase 2: RULES.md mutation, target task only
cp "$RULES" "$BACKUP"
cat >>"$RULES" <<'EOF'

## Scope control (harness-eval experiment mutB)

- Prefer the minimal change that satisfies the request. Do not create test
  files, fixtures, or verification scripts unless the task explicitly asks for
  them; verify your change with quick direct checks instead.
EOF
bash bin/run.sh 04-sh-backup vllm/homelab-default mutB-rules-scope

restore
trap - EXIT
echo AB_DONE
