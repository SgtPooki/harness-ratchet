# Gate v5 spec: the improvement clause gets a materiality rule

Frozen from the spec BEFORE the v5 implementation existed, per the same
discipline that froze the v4 fixtures: expected verdicts here are derived by
reading this spec and doing the arithmetic by hand, never by running the code
they test. The v4 fixtures stay untouched and keep replaying v4 math.

## What changes

Exactly one clause. v4 rule 4 reads:

> a held_in pass-rate gain counts as improvement

where "gain" is any strictly positive change in the summed held-in per-task
pass rates. That is what makes the gate promotable on noise: at k=4 a single
rollout flipping on a single task moves the sum by 0.25 and satisfies
improvement with nothing else required.

v5 rule 4 reads:

> a held_in pass-rate gain counts as improvement only if it is MATERIAL

and material means the aggregate strictly increases AND at least one of:

- **per-task materiality**: some held_in task's pass rate rises by at least
  `material_task_delta` (default 0.5, half its rollouts); or
- **aggregate materiality**: the summed held_in pass rate rises by at least
  `effect` in relative terms (the same threshold the soft axes already use).

Nothing else moves. Rules 1, 2, 3, 4b and 5 are byte-identical to v4, the soft
axis branch is unchanged, and a soft-axis improvement still satisfies rule 4 on
its own.

## Why these two disjuncts

Per-task materiality catches the case the loop exists for: a mutation that
actually fixes a failing task. At k=4 a task going 0/4 to 2/4 is a real change
in behavior, and a single flake is not.

Aggregate materiality keeps broad small gains promotable when there are enough
of them to clear the same bar the soft axes must clear. Without it, a mutation
that lifts five tasks by one rollout each would be rejected while a single
noisy flip on one task was previously accepted, which is backwards.

## Why not a significance test

The gate is deliberately mechanical and reproducible from recorded rows. A
binomial test would need an assumed per-task flake rate that this project has
not measured. Both disjuncts are pure arithmetic over the same aggregates v4
already computes, so the manifest stays auditable by hand.

## Known limitation, recorded rather than hidden

This raises the bar for a true positive as well as a false one. A genuine
improvement that moves one task by exactly one rollout at k=4 no longer counts
on the pass axis alone. That case is indistinguishable from noise with the
evidence available, so the honest response is to require more evidence, not to
promote and hope. Such a candidate can still promote on a soft axis, and can
still be re-run at higher k where the same delta becomes material.

## The regression case this exists for

Two baselines recorded under an identical harness (same standing overlays,
same model, same concurrency, both k=4) must not promote against each other.
Under v4 they do. That pair is fixture `null_identical_harness` below.
