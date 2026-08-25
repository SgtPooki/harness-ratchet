#!/bin/bash
# Ratchet click #2 driver (2026-08-25), split_version 2 era:
#   1. baseline-v5: all 9 tasks k=2, plus 4 extra rollouts on sentinel 04
#      (k=6 total — tightens the pass-rate bound gemini asked for)
#   2. mutation mut-reason-med: models.yml extraBody gains
#      chat_template_kwargs.reasoning_effort="medium" (channel probed live
#      2026-08-25); trap-guaranteed restore
#   3. candidate sweep: all 9 tasks k=2
#   4. gate verdict vs baseline-v5
set -u
cd "$(dirname "$0")/.."

M="$HOME/.omp/agent/models.yml"
BACKUP="$M.cycle3-backup"
restore() { if [ -f "$BACKUP" ]; then mv "$BACKUP" "$M"; echo "models.yml restored"; fi }
trap restore EXIT

# Phase 1: baseline-v5
EXTRA_CONFIG=mutations/ctxslim-v1.yml bash bin/run.sh all vllm/homelab-default baseline-v5 2
EXTRA_CONFIG=mutations/ctxslim-v1.yml bash bin/run.sh 04-sh-backup vllm/homelab-default baseline-v5 4

# Phase 2: apply mutation (ONE surface: models.yml homelab-default extraBody)
cp "$M" "$BACKUP"
python3 - <<'PYEOF'
import os
p = os.path.expanduser("~/.omp/agent/models.yml")
s = open(p).read()
old = """            chat_template_kwargs:
              enable_thinking: true"""
new = """            chat_template_kwargs:
              enable_thinking: true
              reasoning_effort: medium"""
assert old in s, "models.yml shape changed; aborting mutation"
open(p, "w").write(s.replace(old, new, 1))
print("mutation applied: reasoning_effort=medium")
PYEOF

# Phase 3: candidate sweep
EXTRA_CONFIG=mutations/ctxslim-v1.yml bash bin/run.sh all vllm/homelab-default mut-reason-med 2

# Phase 4: restore, then gate
restore
trap - EXIT
python3 bin/gate.py baseline-v5 mut-reason-med
echo "CYCLE3_DONE gate_exit=$?"
