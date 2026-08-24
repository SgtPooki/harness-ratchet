# harness-eval

Baseline eval pack for harness-engineering iterations on the omp (oh-my-pi)
agent harness, per the observability-driven loop in
[Agentic Harness Engineering](https://arxiv.org/abs/2604.25850): score the
harness before and after each mutation; keep only what measurably helps.

## Layout

- `tasks/<name>/prompt.md` — what the agent is told
- `tasks/<name>/workspace/` — the code the agent works on (copied per run)
- `tasks/<name>/verify/` — hidden verifier (never shown to the agent); plain
  python3/node, zero dependencies, prints `PASS` and exits 0 on success
- `tasks/<name>/solution/` — reference solution overlay, used only by the oracle
- `bin/oracle.sh` — solvability gate: unmodified workspace must FAIL, workspace
  + solution must PASS, for every task. Run after any task edit.
- `bin/run.sh <task|all> [model] [label]` — copies the workspace, runs
  `omp -p --auto-approve --model <model>` with the prompt, verifies, appends to
  `runs/<label>/results.jsonl` (transcript saved alongside)

## Tasks (failure surface each targets)

| task | surface |
|---|---|
| 01-py-pagination | minimal-edit debugging, boundary reasoning |
| 02-py-config-type | cross-file tracing, fix-at-the-right-layer |
| 03-js-slugify | spec-following, edge cases |
| 04-sh-backup | shell/terminal competence (quoting, find -print0) |
| 05-py-dedupe | constraint-following refactor (structural checks) |
| 06-py-version-sync | codebase search, consistency |

## Rules

- Never show the agent anything under `verify/` or `solution/`.
- A task only counts while `bin/oracle.sh` is green.
- One variable at a time: change one harness component between labeled runs.
