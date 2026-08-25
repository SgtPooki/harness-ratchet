# CONTEXT — vocabulary and invariants

Terms are used in exactly these senses across code, docs, and commits.
If a change needs a term to mean something else, change this file first.

## Core terms

- **harness** — everything around the frozen model that shapes its behavior:
  prompts, rules, context files, config, tool wiring, compute budgets. Here,
  specifically omp's exposed surfaces.
- **surface** — one mutable part of the harness (e.g. `RULES.md`, a playbook
  file, `models.yml` extraBody). The mutation agent may only touch declared
  surfaces.
- **mutation** — ONE change to ONE surface, tied to a named failure pattern,
  evaluated as a labeled candidate run. Never batched.
- **channel** — the path by which a mutation reaches the model (RULES.md,
  trust-header append). Channels must pass a **liveness probe** (observable
  token test) before any A/B that uses them.
- **task** — prompt + workspace + hidden verifier (+ reference solution +
  sabotage variant). Lives in `tasks/<name>/`.
- **verifier / oracle** — the mechanical checker for one task. The **oracle
  gate** (`bin/oracle.sh`) audits verifiers: unmodified fails, solution
  passes, sabotage fails.
- **sabotage** — a deliberately-wrong (usually partial-fix) solution used to
  prove a verifier can detect wrongness. REQUIRED for minted/admitted tasks;
  optional for the hand-authored bootstrap pack (present: 01, 04, 07) —
  oracle.sh audits it only where present.
- **rollout** — one agent attempt at one task (`run_$k`). **k** — rollouts
  per task; gate minimum is 2.
- **pack** — a distributable directory of tasks plus a `pack.json` manifest;
  identified by its **pack digest** (hr-pd-1) and its **vintage** (monotonic
  integer + publication date; any content change is a new vintage). Packs
  never dictate split roles.
- **task surface** — one of a task's three audiences: agent surface (prompt,
  workspace), scoring surface (verifier), admission surface (solution,
  sabotage). Distinct from **surface** above, which is a mutable part of the
  HARNESS. Each task surface carries an encryption field (plaintext or
  role-keyed).
- **admission record** — per-task `admission.json`: the miner's audit
  attestation (oracle triple, mutant kills, stability). Never authoritative;
  consumers re-execute the audit.
- **finding** — the unit of publication: one mutation (as a single
  **surface operation** on one declared surface) plus its claim schema,
  evidence, and replication instructions; identified by its hr-fd-1 digest.
  kind: improvement or negative-result.
- **standing overlays** — infrastructure config applied identically to BOTH
  arms of a comparison (e.g. eval isolation, previously promoted overlays).
  Part of a finding's baseline_harness block; never part of the mutation.
- **bootstrap pack** — the nine public tasks in this repo's `tasks/`,
  kept permanently as demo and floor rails (already public, so burned as
  headroom by definition). The operator's **personal bank** is a separate,
  never-published pack plus era state; it starts empty of these.
- **split** — the pinned assignment in `split.json`: **held-in** (visible to
  proposers), **held-out** (non-regression floor, never shown to proposers),
  **sentinel** (never optimized against; drift canary only).
- **gate / pawl** — `bin/gate.py`; the only thing that promotes or rejects.
  Gated soft axes (v1.1): duration_p50, tokens_out_p50, tokens_in_p50; a
  held-in pass-rate gain also satisfies the improvement requirement.
  **composite pass** — verifier PASS **and** agent exit 0.
- **manifest** — immutable per-candidate record: decision, evidence, split
  version, rollback target.
- **ledger** — RESULTS.md; the committed human-readable history.
- **ratchet click** — one full cycle: mutate → rollouts → gate → promote or
  rollback.

## Invariants (violations are bugs, not choices)

1. Nothing the optimizer influences may own the scoreboard.
2. Verifiers are never authored by whatever proposes tasks or mutations.
3. Sentinel tasks never gate and are never optimized against. Running a
   mutation cycle that targets a sentinel invalidates the candidate. (mutA/
   mutB targeted 04 before the split existed; that is why this is written
   down.)
4. Manifests are immutable; the gate refuses to overwrite one.
5. One mutation per candidate label (process-enforced via the manifest's
   declared surface; not yet mechanically verified).
6. Agents never see `verify/`, `solution/`, or `sabotage/`.
7. Weakness mining draws failure specimens from held-in and sentinel runs
   ONLY. Mining a held-out failure to design a mutation is optimizing
   against the floor (cycle-4 operator error; the gate made the peek
   unprofitable, this rule makes it illegal).
