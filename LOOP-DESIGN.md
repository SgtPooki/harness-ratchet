# Self-improving harness loop — v2 (post peer-review + literature survey)

Status: v2, 2026-08-24. v1's central claim survived triple peer review (codex,
gemini, cursor — unanimous SOUND-WITH-REFINEMENTS) and an 11-paper verified
survey (see notes/projects/agentic-automation-research.md, 2026-08-24 entry).
Context: omp + Qwen3.8-27B (thinking, DFlash2) on one RTX 5090; gpt-oss-20b
advisor on a Mac; no fine-tuning/LoRA.

## The claim, as refined

v1: "task generation can be automated, but verification must stay mechanical
(execution-based) and outside the loop's reach."

What survived: the optimizing agent must never own the scoreboard. Persistent
changes (harness edits, task admissions) are decided only by frozen, mechanical,
agent-inaccessible signals. (Support: AHE, Self-Harness, ICLR'25
self-critique-collapse results, our own Ornith + task-04 specimens.)

What was refined by review:
- "Execution-ONLY" was too strong. LLM machinery is legitimate INSIDE the loop
  when it cannot touch the scoreboard: reflection, tool-integrated
  self-verification during solving (T1'25), judge ENSEMBLES as advisory
  signals, and judges as VETOES/cost functions (a veto resists Goodharting
  because it's a constraint, not a target — gemini). Two-tier split (cursor):
  TERMINAL oracle decides keep/revert; DIAGNOSTIC layer only proposes.
- Generators must not author verifiers (v1 had this wrong). FeatureBench
  pattern instead: excise features along dependency graphs of EXISTING
  human-written tests — task generation stays generative, oracles stay
  human-written-at-origin.

## Architecture (composed from Self-Harness + FeatureBench + ACE + GEPA)

1. TASK MINT (offline, CPU): FeatureBench-style test-excision over our own
   repos + REAP-style admission gate (multi-run stability; flaky = rejected).
   Hard held-in/held-out split; held-out never visible to any proposer.
   Plus a never-optimized SENTINEL set as canary.
2. ORACLE GATE (bin/oracle.sh): per task — unmodified FAILS, solution PASSES,
   sabotaged solution FAILS (verifier-robustness audit; REQUIRED for generated
   tasks, present for 01/04/07). Roadmap: hidden verify bank + coverage floor.
3. ROLLOUT (bin/run.sh): k≥2 rollouts per task (DemoEvolve: k=1 promotes
   luck). Telemetry: pass, duration, tokens, tool calls, patch size.
4. WEAKNESS MINING (Mac advisor): categorize failed traces into named failure
   patterns (Self-Harness stage 1) from omp session logs.
5. MUTATION PROPOSAL: ONE edit per iteration (AHE: effects are non-additive),
   tied to a named failure pattern, with an AHE-style predicted-impact record.
   Evolvable surfaces: ACE-style playbook (delta-only, size-capped, curated),
   prompts (GEPA for this subset), tool descriptions, compute budgets
   (timeouts/retry policy — gemini R3).
6. PROMOTION GATE (mechanical only):
   a. held-in improvement AND held-out non-regression across k runs;
   b. minimum effect size (DemoEvolve noise floor);
   c. Pareto check across {pass, duration, tokens, patch size} — no axis
      collapse (codex/cursor; the mutB lesson);
   d. TTSC control: if matched best-of-N on the PRE-mutation harness closes
      the same gap, reject as non-durable search (cursor, arXiv 2607.12227);
   e. prediction-vs-outcome attribution: edits whose predicted flips don't
      materialize get reverted even if aggregate rose (AHE: self-predicted
      safety was ~11% precise — never trust it).
7. VETO LAYER (advisory, cannot pass anything): gpt-oss simplicity veto on
   execution-passing solutions ("over-engineered/out-of-scope? Y/N") — the
   task-04 fix; advisor watchdog on transcripts for degenerate strategies.
8. REAL-WORK LANE: periodic scoring on actual repo tasks with veto power to
   halt the loop (the Ornith two-lane lesson).

## Top Goodhart risks (review-ranked)

1. Verifier-shaped shallow tasks: generator converges on what is easy to
   verify → guard 2 (sabotage audit) + admission quotas by difficulty band +
   REAP anchoring to real usage prompts.
2. Held-in overfitting: guard 6a/6e + periodic pool refresh.
3. Selection noise promoted as improvement: guards 3, 6b, one-edit-at-a-time.
4. Playbook collapse/bloat (ACE's own catalog): delta-only updates, size cap,
   Generator/Reflector/Curator separation.

## Build order

1. ✓ Oracle sabotage audit (this commit)
2. Simplicity-veto judge wired into run.sh post-verify (gpt-oss)
3. Pareto ledger fields in results.jsonl + k=2 rollouts
4. FeatureBench-style excision miner over homelab2/engops/vllm-proxy
5. Weakness-mining pass over accumulated omp session logs (Mac advisor)
6. First full loop iteration (one mutation, full gate)
