# harness-ratchet PRD

Status: v1 draft, 2026-08-24. Scope authority: changes to Goals/Non-goals
require an explicit entry in this file's changelog, not a code commit.

## Problem

A capable local model (Qwen3.8-27B on one RTX 5090) is bottlenecked by its
harness, not its weights. Manual harness tuning is unmeasured and regresses
silently. Published loops assume cloud models, owned agents, or public
benchmarks the model has memorized.

## Goal

One operator can run an unattended loop that measurably improves the omp
harness around a frozen local model, where every accepted change has passed
mechanical evidence gates, and every rejected change has a recorded reason.

## Users

- Primary: the operator (Russell) improving his own omp + Qwen3.8 stack.
- Secondary: local-LLM users who fork the pattern. We do not build FOR them
  yet; we only avoid gratuitously blocking them.

## Success metrics (announcement-grade, all mechanical)

1. ≥1 mutation PROMOTED through the full gate with held-out non-regression.
2. Measured improvement on ≥1 gated axis (held-in pass rate, duration_p50,
   tokens_in_p50, or tokens_out_p50) vs the pinned baseline label
   `baseline-v2`, at k≥2 with gate --effect 0.15 met (pass-rate gains exempt
   from the effect threshold).
3. Zero silent regressions: every accepted change has a manifest, and
   rollback is mechanical: `git checkout <manifest.rollback_target> -- <surface files>`
   restores the pre-mutation harness.
4. Task pool refresh works: ≥5 minted-from-own-repo tasks admitted through
   the oracle (incl. sabotage audit) without hand-authoring verifiers.

## In scope (v1)

- The loop: runner, oracle (with sabotage audit), gate, ledger, manifests.
- Mutation surfaces: omp RULES.md, context/playbook files, models.yml
  extraBody, trust-header appended prompt, compute budgets (timeouts).
- Simplicity-veto judge (gpt-oss, advisory).
- Weakness mining from omp session logs (Mac advisor).
- FeatureBench-style excision miner over the operator's own repos.
- Hand-authored task pack as bootstrap fuel.

## Non-goals (v1) — the scope fence

- NO multi-harness adapter layer until a second harness is actually in use.
- NO model fine-tuning, LoRA, or weight changes of any kind.
- NO cloud models inside the loop (peer review of the TOOLING is fine;
  cloud agents never review code diffs — standing house rule).
- NO automated mutation-proposal agent until ≥3 manual gated iterations have
  taught us the failure taxonomy (per the adopted Self-Harness discipline).
- NO benchmark chasing: Terminal-Bench/SWE-bench numbers are out of scope;
  the real-work lane and own-repo tasks are the truth.
- NO web UI, dashboard, or service; CLI + files only.
- NO upstreaming into auto-harness/Harneloop; ideas may be ported IN.
- NO changes to tasks, verifiers, split.json, bin/, model, provider, engine,
  or runtime during a candidate A/B — a candidate varies exactly ONE declared
  harness surface (the loop may never mutate its own scoreboard).
- NO mutation cycles targeting sentinel tasks; a run that optimizes against a
  sentinel is invalidated.

## Someday (explicitly post-M5, kept here so it doesn't creep)

- Author a harness challenge on yukon.org (the autoresearch-challenge
  platform behind mlxfast): pinned local model + locked loop + editable
  harness surfaces + HIDDEN task bank scored by bin/gate.py. Yukon supplies
  platform/queue/leaderboard, so the "no service" fence is NOT the blocker —
  the prerequisite is M4 (excision miner mints tasks solvers have never
  seen). Revisit after M4. Their conventions worth porting sooner:
  editablePaths-style surface manifest (mechanizes invariant 5),
  Fiat-Shamir-derived task inputs. (homelab2#246 tracks the solver/technique
  side.)

## Milestones

- M1 (done): oracle-verified pack, runner v2, pinned split, gate; baseline-v2.
- M2: first full gated mutation cycle (mutate → k=2 → gate verdict → keep or
  rollback), with the simplicity veto advisory in place.
- M3: weakness-mining report from session logs feeding mutation selection.
- M4: excision miner mints and admits ≥5 tasks; pool refresh documented.
- M5: announcement with before/after numbers.

## Changelog

- 2026-08-24: v1 drafted; sent to peer review alongside CONTEXT.md.
- 2026-08-24: v1.1 — review edits: exact gated axes + pinned baseline in
  metric 2, mechanical rollback definition, scoreboard-immutability and
  sentinel fences added (codex/gemini/cursor round).
