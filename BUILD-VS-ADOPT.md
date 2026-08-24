# Decision: build our loop vs. adopt an existing OSS chassis

Status: DECIDED 2026-08-24 — **Build forward (A′ / "Ruthless A")**. Triple
peer review (codex "C-minus", cursor "A′", gemini "Ruthless A") converged:

- Do NOT adopt auto-harness as chassis (architectural mismatch: it optimizes
  its own agent.py; our artifact is a closed external CLI). Port its gate
  PATTERNS as ~200 lines of local tooling.
- Do NOT build the adapter interface now (2-of-3; codex wanted a single-file
  minimal one). Hardcode omp; revisit when a second harness is actually used.
  Keep codex's `channel_liveness_probe` idea when that day comes.
- Unanimous build-order correction: THE GATE FIRST. Current promotion is "a
  sieve, not a gate" (gemini). Implement k=2 rollouts, held-in/held-out split,
  pass + duration Pareto axes, minimum effect size, immutable per-run evidence
  manifest — BEFORE veto judge, weakness mining, or the excision miner. Prove
  one mechanical promote/reject decision end-to-end, then expand.
- Accepted risks: gate-math bugs (mitigate: keep it boring, test it), task
  starvation later (excision miner is cycle 2), omp-overfitting (accepted —
  omp IS the product; portability was explicitly secondary).

## Round-2 cross-examination (each reviewer saw all round-1 reviews)

Verdicts: codex CONFIRM, cursor CONFIRM-with-AMEND, gemini AMEND. Strategic
decision unchanged (build forward, no adapter, no chassis adoption — the
auto-harness claim was re-validated against its README with narrower wording:
"does not directly fit improving omp without refactoring", not "cannot ever").

New defects round 2 caught that round 1 (and we) missed:

1. **`pass=true` on timeout** (cursor): mutB recorded pass=true with rc=124 —
   gate success must be composite: `verifier PASS && agent_rc==0`.
2. **run.sh clobbers rollouts** (gemini): `rm -rf $work` + fixed transcript
   path destroy the first rollout's evidence — k=2 needs `run_$k` subdirs
   structurally, not just gate math.
3. **No pinned task split** (codex): without a committed held-in/held-out/
   sentinel assignment file, k=2 comparisons aren't stable and the loop can
   move its own goalposts.
4. **The 8/8-pass trap** (gemini): with pass saturated, a pass+duration gate
   optimizes ONLY duration → promotes laziness. Accepted-with-guard: held-out
   pass non-regression is the hard floor (laziness that breaks correctness
   shows up there); token telemetry added so duration isn't the sole soft
   axis; REVISIT when the excision miner restores pass headroom.
5. Four-axis Pareto is aspirational (cursor): no token/tool telemetry exists
   yet; gate v1 = pass (hard) + duration_p50 + tokens (soft).
6. Manifest: minimal local `manifest.json` (mutation id, surfaces, probe
   results, rollback target) — no Harneloop dependency (cursor/gemini,
   overriding codex's heavier version).

**AMENDED single first action (supersedes the round-1 one):**
(1) Fix run.sh: `run_$k` subdirs, composite pass, token extraction from
transcripts; (2) commit a pinned `split.json` (held-in/held-out/sentinel);
(3) implement `bin/gate.sh` as a SEPARATE script reading results.jsonl —
k=2 aggregation, held-out pass non-regression (hard), min-effect-size on soft
axes, minimal manifest emission; (4) prove end-to-end by mechanically
REJECTING mutB-rules-scope vs baseline using data already in runs/.
No adapter YAML, no chassis adoption, no new tasks until the gate stands.

Original decision framing follows.

---

Status: DRAFT under peer review, 2026-08-24. Companion to LOOP-DESIGN.md (v2).

## Context

We designed a self-improving harness loop (LOOP-DESIGN.md): own-repo task
minting with human-written-at-origin oracles, sabotage-audited verifiers,
Self-Harness-style held-in/held-out promotion gates, fully local (omp +
Qwen3.8-27B on one RTX 5090; gpt-oss-20b advisor on a Mac). A pack of 8
oracle-verified tasks, runner, and results ledger already exist in this repo.

OSS prior art (all surveyed today):

- **neosigmaai/auto-harness** (535★, MIT): failure mining → coding agent edits
  `agent/agent.py` (its OWN bundled agent) → 3-step gate (regression check,
  test-split validation, suite promotion). Consumes existing benchmarks via
  `BenchmarkRunner` subclasses (Harbor/tau-bench/TB2). Designed for Claude
  Code/Codex CLI as the EDITOR agent; cloud API keys assumed. No task
  generation, no verifier audit, no documented local-model support. Its
  mutation surface is its own agent.py — NOT an external harness like omp.
- **china-qijizhifeng/agentic-harness-engineering** (848★): official AHE code;
  evolves 7 harness component types with git-revertible file representations;
  sized for ~96 concurrent sandboxes and frontier-model evolve agents.
- **Ker102/Harneloop** (4★, v0.0.2 alpha, Apache-2): evidence-gated promotion,
  immutable runs, environment-agnostic BYO-agent (command/MCP/manual modes).
  User-supplied tasks, no verifier audit, pre-1.0 churn expected.

## The custom-harness question

omp is an external, closed-loop CLI harness: we can mutate its RULES.md,
context files, model config, and (with the trust-header workaround) system
prompt — but NOT its internal agent loop. Of the three: Harneloop is the only
one designed for that shape (command-driven BYO-agent). auto-harness mutates
its own bundled agent — adopting it means replacing omp, not improving omp.
AHE assumes you own all 7 component types (we own ~4 of omp's surfaces).

## Options

A. **Build forward on harness-eval** (current path): full control, local-first,
   our three unshipped pieces stay ours; cost: we re-implement gate machinery
   that auto-harness already has, and maintain it.
B. **Adopt auto-harness as chassis**, contribute local-model + BYO-harness +
   verifier-audit + task-minting upstream: leverage 535★ momentum; cost: its
   architecture assumes it owns the agent; retrofitting BYO-harness may be a
   rewrite-in-disguise; cloud-agent assumptions run deep.
C. **Hybrid** (proposed): keep harness-eval as the vehicle; PORT auto-harness's
   proven gate patterns and Harneloop's evidence-manifest idea; define a thin
   HARNESS ADAPTER interface so the loop is omp-first but not omp-only:

   ```yaml
   # adapter contract (sketch)
   harness:
     run: "omp -p --auto-approve --model {model} {prompt}"   # exec template
     surfaces:                    # what the mutation agent may edit
       rules:   ~/.omp/agent/RULES.md
       playbook: ~/.omp/agent/PLAYBOOK.md      # ACE-style, ours
       config:  ~/.omp/agent/models.yml
     telemetry:
       sessions: ~/.omp/agent/sessions/        # trace mining source
     quirks:
       append_system_prompt: trust-header-wrap  # omp-specific workaround
   ```

   Another harness (claude -p, codex exec, opencode, …) = another adapter file.
   Portability is a side effect, not a goal (less focus, per the operator).

## Questions for reviewers

R1. Given the constraint set (external un-editable harness, fully local models,
    single GPU, one maintainer with limited time), is A, B, or C the right
    call? What would change your answer?
R2. Is the adapter contract above the right abstraction boundary, or does real
    portability require more (per-harness failure-pattern taxonomies,
    per-harness mutation channels)? Is it worth even this much generality now?
R3. What's the strongest argument for B (adopt) that we're underweighting —
    e.g. maintenance burden of gate machinery, community task pools, or
    auto-harness's trajectory making our pieces redundant within months?
R4. If C: which auto-harness/Harneloop pieces should be ported FIRST, and
    which of our build-order items (veto judge, Pareto ledger, excision miner)
    should yield priority to that porting?
