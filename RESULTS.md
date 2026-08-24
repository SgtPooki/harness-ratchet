# Results ledger

One row per labeled run set. Raw JSONL + transcripts live under `runs/` (gitignored);
this file is the committed record.

## baseline-qwen38-thinking — 2026-08-24

Harness: omp v18.0.4 defaults, `-p --auto-approve`, model `vllm/homelab-default`
(qwen38-27b-dflash2 engine, thinking ON via extraBody, temp 0.2, k=5 DFlash2).

| task | pass | duration |
|---|---|---|
| 01-py-pagination | PASS | 80s |
| 02-py-config-type | PASS | 135s |
| 03-js-slugify | PASS | 136s |
| 04-sh-backup | PASS | 790s |
| 05-py-dedupe | PASS | 80s |
| 06-py-version-sync | PASS | 86s |

**6/6 pass, 1307s total.** (Smoke run of 06 before the sweep: also PASS, 75s.)

Findings:

1. **No pass/fail headroom** — the pack is too easy for qwen3.8-thinking. Until
   harder tasks land, the primary metric for harness A/Bs is duration (and,
   once mined from session logs, tokens/tool-calls).
2. **04-sh-backup took 10x the median** — transcript shows the agent built its
   own 42-file hostile fixture set and a private verify.sh, iterating to
   perfection (it even handled newline-in-filename, beyond our verifier).
   Self-imposed rigor, not flailing. Mutation candidate: prompt-level scope
   control ("make the minimal fix") vs keeping the rigor. Decide with data.
3. `omp -p` transcripts are final-text only (~0.5KB); real trace mining (step 2
   of the loop) needs omp's session store (`~/.omp/agent/sessions`, agent.db).

Next: add 2-3 harder tasks (multi-step, larger codebase, ambiguous spec) for
pass/fail headroom; then run the first mutation A/B.
