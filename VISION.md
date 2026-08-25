# VISION: where harness-ratchet is going

Status: ratified 2026-08-25. This document names the
destination and the constraints every design decision must respect. PRD.md
owns current scope; when the two disagree, PRD.md governs today's work and
this file governs where it must remain able to go. Where PRD.md sketches a
competition-style challenge as a possible future, this file supersedes that
in intent: competition is an optional module, never the trunk.

## Destination

A replication network for harness findings. Operators run a CLI loop that
measurably improves the harness around their own frozen local model, and a
public registry consolidates the mutations that worked, each one a
falsifiable, replicable claim, so anyone running a similar harness or model
can apply them. Reputation accrues to findings that replicate, not to ranked
competitors. Everything runs local-first: solvers keep their models, their
hardware, and their private code.

The destination constrains architecture; it schedules nothing.

## Who this is for

**The operator** runs a capable local model that underperforms its
potential, and suspects the bottleneck is the harness (prompts, rules,
context files, compute budgets). They run the loop as CI for their harness:
mint tasks from their own code, record a baseline, and test one mutation at
a time against mechanical gates. The benefit: a measurably better harness
for their daily stack, with every change evidenced and every regression
caught, instead of vibes-driven config tweaking that regresses silently.

**The reader** may never run the loop. They arrive at the dashboard with a
stack in mind ("qwen-class model on omp") and leave with mutations worth
trying tonight, each carrying its effect size, its conditions, and its
replication record. The benefit: skipping the experimentation other people
already paid for. Most users are readers; the network is built to serve
them.

**The contributor** runs the loop and publishes what worked, or adds tasks
and validators to the commons. The benefit: reputation attached to findings
that replicate, other people's replication data on their own discoveries,
and better instruments for their own loop.

## The three jobs

1. **The loop**: help a single user run a CLI ratchet that improves their
   harness for their model, where every accepted change passed mechanical
   evidence gates and every rejection has a recorded reason.
2. **The registry**: consolidate findings that improved things into a public
   dashboard, grouped by harness and model family, so others can see what to
   try on their own stack.
3. **The commons**: let others contribute task candidates and validators
   through role-separated admission (a proposer never authors the verifier
   that admits their own task), so everyone's improvements get faster and
   better measured.

## The artifacts

**The kit** is this repository. Its embeddable core is the **verification
kernel**: oracle admission (a task is admitted only when the unmodified
workspace fails its verifier, the reference solution passes, and a
deliberately sabotaged solution fails), the promotion gate, the split and
era registry (versioned held-in/held-out/sentinel task assignments and
pinned comparison baselines, so results from different eras are never
compared), and the manifest and claim schemas. Task minting (excising a
function from a real module and using its existing human-written tests as
the hidden verifier) is a producer that feeds the kernel, not part of it.
Harness invocation is a pluggable runner interface. The reference runner
drives omp, a CLI agent harness, and stays the only runner until a second
harness is actually in use: the interface is an internal boundary, not a
multi-harness adapter layer. "Embeddable" means the kernel, never a runner.
The kernel makes no assumptions about any particular machine and is callable
as a library.

**Task packs** are the data. A pack is a directory of tasks in a standard
layout plus a manifest with a version and publication date (its
**vintage**). Packs live outside the kit (the kit's bootstrap `tasks/`
directory will be externalized), and the runner takes a pack path as input.
Exactly two shapes exist before any hosted service: **public packs**
(published, vintage-dated, anyone can score against them) and **personal
banks** (never leave the author's machine). A pack physically contains code,
so no shape exists where code stays private to its author while strangers
execute it.

**Findings** are the unit of publication. A finding is the mutation artifact
itself (a config overlay, a rules edit) plus its claim schema and evidence
manifests, with instructions to replicate. The claim schema pins everything
the claim depends on: kit commit, gate version, pack digest and vintage,
split digest, model fingerprint (a hash identifying the exact weights, and
the family bucket the dashboard groups by), harness-surface digest, baseline
label, and runtime envelope (engine, quantization, compute budgets). A claim
missing schema fields is not admissible to the registry.

## Trust model

An operator's own loop is **self-trusted**. Its invariants (the optimizer
never owns the scoreboard, verifiers are never authored by proposers,
held-out tasks are never mined for mutation ideas) exist to prevent
self-deception, the failure mode that actually threatens a single user.

The registry is **replication-trusted**, and precise about what replication
means. Findings are self-reported and labeled as such: evidence files
produced on a submitter's own machine cannot be proven honest, because the
submitter controls the machine, the runner, and the telemetry. Credibility
accrues through follow-up runs, tallied in three separate lanes:

- **Exact replication**: the same public pack, split, and claim conditions.
  Reproduces the claim itself, and is auditable because the pack is public.
- **Local transfer**: the finding re-tested through the replicator's own
  loop, against their own bank and baseline. This does not reproduce the
  submitter's numbers; it answers the question a reader actually has: does
  this mutation help on a different stack? Transfer runs against private
  banks are themselves unverifiable and are labeled accordingly.
- **Registry re-run**: the registry re-executes the claim on its own
  reference hardware (load the pinned open-weights model, apply the pinned
  mutation, run the same gate on the same public pack). A claim that
  reproduces this way earns a verified badge requiring no trust in the
  submitter. Its limits are capacity, not principle: only public-pack claims
  with obtainable weights that fit the reference hardware qualify, runs are
  queued and prioritized by model-family popularity, and the verifier's word
  replaces the submitter's. That trade is acceptable because the registry
  stakes its own reputation on it.

Replicated and refuted are mechanical verdicts (the replicator's promotion
gate, recorded in a replication manifest), never opinions. The loop
broadcasts refutation manifests by default when a fetched finding fails
locally, so negative results are first-class tallies rather than silently
discarded. A refuted finding is not necessarily dishonest: overfitting to
the submitter's stack is the common cause, and the registry filters for
robustness, not only honesty.

Stated limits, held openly: a young registry is a catalog of try-me claims,
and every entry stays provisional until independent operators replicate it.
Registry identity anchors to real accounts; stronger resistance to
manufactured identities waits for a hosted module that needs it. The
registry's honesty story is falsifiability, not proof.

Competition (hidden task banks, key ceremonies, attested runners, the
classic competition-server shape) is an **optional future module** the
network can host once it exists, never the trunk. Adversarial ranking has
requirements the registry deliberately avoids: server-side scoring, and
hosted or fingerprint-pinned models, since bring-your-own-model claims are
unverifiable when weights can be tuned on published tasks. Those are the
competition module's costs, paid only if it is ever built.

## Oracle secrecy

A task has three surfaces: the **agent surface** (prompt and workspace:
plaintext, what the model works on), the **scoring surface** (the verifier),
and the **admission surface** (reference solution and sabotage variant). The
pack format reserves an encryption field per surface (plaintext or
role-keyed) so hidden-oracle packs need no format change later. Encryption's
scope is process hygiene: it mechanically enforces "the agent process never
sees the verifier" (a filesystem-wandering agent finds ciphertext), and it
enables future modules. It is not a competitive trust boundary: a human who
can run a verifier can read it.

## Task sourcing and contamination

Public code is presumed present in every model's training data, and
continuous scraping keeps shrinking the window of unseen public code. The
policy:

- **Headroom tasks** are hard tasks the subject model cannot yet pass
  reliably, the ones that make an improvement visible. They are minted from
  private code and stay in personal banks. Every replicator measures
  findings against their own headroom, so the commons never needs public
  headroom.
- **Public packs** are floor and regression rails: minted from code merged
  after the subject models' training cutoffs where recency matters,
  vintage-dated always, and treated as ephemeral epochs. A vintage is an era
  marker, not an eternal benchmark.
- Public packs are untrusted code: contribution runs the full mechanical
  admission audit in CI, and consumers get sandbox guidance (no network by
  default, resource limits).
- No anonymization layer: renaming does not hide structure. Code either is
  publishable or stays in a personal bank.

**Task minting is the core bottleneck of the whole vision**, not a format
detail. Before any registry work, the miner must prove repeatability: on the
order of ten admitted tasks from at least two source repos, with admission
failure reasons, flake rate, and sabotage quality measured. This bar is
deliberately stricter than the loop's own task-pool milestone in PRD.md;
registry work waits on it.

## Sustainability

Public and reputation-first. If adoption arrives or parts start costing real
money to run (a hosted dashboard, curation, the re-runner, a competition
module), charging for those parts becomes a decision to make then. Nothing
in this architecture forecloses it, and nothing depends on it.

## Non-goals until the destination demands them

Multi-language task miners, LLM re-theming of tasks, any hosted service, the
competition module, and adversarial-submission review all wait for the stage
that needs them. The single-user loop keeps its own scope fence in PRD.md.

## Staged path (each stage independently valuable)

1. Kernel extraction: a configuration-driven runner built on the
   kernel/runner boundary, with packs external to the kit.
2. The first personal bank as an external pack (plaintext; encryption is a
   later field, added when a second trust domain exists), and the miner
   repeatability milestone.
3. Finding format v1 and a registry repo, seeded with replicable findings
   ("try this on your stack").
4. Static dashboard over the registry: findings grouped by harness and model
   family, with the three replication lanes tallied separately.
5. Reference re-runner: a queue that re-executes qualifying claims on the
   registry's own hardware and issues verified badges. The first hosted
   piece, far cheaper than a competition platform.
6. Optional modules, if the network pulls for them: encrypted-oracle packs,
   hosted scoring at scale, a competition challenge.
