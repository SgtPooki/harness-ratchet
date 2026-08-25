#!/bin/bash
# Ratchet click #3 (2026-08-25): mutation mut-maxtok-48k.
# Weakness mining found 09 r1 died at stopReason=length — 32,861 tokens_out
# at the 32768 cap, one thinking spiral, no action ever taken. Mutation:
# models.yml homelab-default maxTokens 32768 -> 49152 (ceiling, not thinking).
# Compares against baseline-v5 (same split_version 2 era).
set -u
cd "$(dirname "$0")/.."
M="$HOME/.omp/agent/models.yml"
BACKUP="$M.cycle4-backup"
restore() { if [ -f "$BACKUP" ]; then mv "$BACKUP" "$M"; echo "models.yml restored"; fi }
trap restore EXIT

cp "$M" "$BACKUP"
python3 - <<'PYEOF'
import os
p = os.path.expanduser("~/.omp/agent/models.yml")
s = open(p).read()
old = """      - id: homelab-default
        name: Qwen3.8-27B (thinking)
        contextWindow: 122880
        maxTokens: 32768"""
new = """      - id: homelab-default
        name: Qwen3.8-27B (thinking)
        contextWindow: 122880
        maxTokens: 49152"""
assert old in s, "models.yml shape changed; aborting"
open(p, "w").write(s.replace(old, new, 1))
print("mutation applied: maxTokens=49152")
PYEOF

EXTRA_CONFIG=mutations/ctxslim-v1.yml bash bin/run.sh all vllm/homelab-default mut-maxtok-48k 2

restore
trap - EXIT
python3 bin/gate.py baseline-v5 mut-maxtok-48k
echo "CYCLE4_DONE gate_exit=$?"
