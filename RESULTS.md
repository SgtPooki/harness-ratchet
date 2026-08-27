# Results ledger

## Registry seeded — 2026-08-27 — stage 3 complete

harness-registry holds its first three objects: the
contract-discipline-rules negative-result finding (private-pack task
ids anonymized per the finding-format amendment) and its two
replications, an exact-lane environment-mismatch and a local-transfer
replicated verdict. The transfer re-run also gave the early-abort
machinery its first production firing: held-out 09 dropped a rollout
against a 1.00 baseline floor, the certainty condition triggered
mid-sweep, the remaining rollouts were skipped, and the resulting
REJECT agrees with the claim. An earlier attempt at this replication
was discarded by the book when concurrent model load contaminated its
duration axis; the published run is from a verified-quiet machine.

Two robustness fixes fell out of the day's dogfooding: trap-restore now
survives SIGTERM and SIGINT (a killed sweep once left its rules block
applied), and the registry validator computes a finding's hr-fd-1
excluding its nested replications, which are attachments per the
replication resolution.

## First replication — 2026-08-27 — the pipeline closes its own loop

The contract-discipline finding was replicated through the shipped
replicate verb, both lanes exercised on real objects. Exact lane:
stage-A pin checks correctly produced an environment-mismatch manifest
(the claim touches a private pack, unobtainable by anyone else;
recorded, never tallied). Transfer lane: a full k=4 re-run through the
replicator's own loop whose gate REJECT agrees with the negative-result
claim, outcome replicated, private task ids anonymized to stable
t1/t2-style ids with difficulty bands before the evidence left the
machine. Dogfooding caught and fixed two real defects first: replicated
now means the replicator's verdict AGREES with the claim (a REJECT
confirms a negative result), and the replicator's concurrency comes
from the runner, not the operator envelope file.

Every stage of VISION stages 1 through 3 has now executed at least once
on real data: mint, audit, baseline, probe, click, export, replicate,
and the registry repo with its mechanical merge gates. Registry seeding
waits on one amendment (private-pack task ids anonymized in finding
split blocks, the #7 principle extended to findings).

## mut-contract-lean-k4 — 2026-08-27 — **REJECTED** at claim grade; the first finding

The lean contract rule re-proposed at k=4 under the locked re-proposal
path, aimed at making the cycle-7 verdict claim-grade. It did more than
that: the k=2 screenings' held-in pass gain (03 at 2/2 twice) vanished
at k=4, exposed as 2-sample luck, exactly the false positive the
escalation rule exists to catch. The k=4 truth is pure cost: held-in
duration_p50 +18 percent, held-out duration_p50 +37 percent, held-out
tokens_out_p50 +17 percent, no improvement on any axis, and the target
task untouched (16 at 0/4 under the rule, matching baseline). Sweep:
3919s, 15.3M tokens_in, 36 rollouts, sentinels skipped on the reject.

Exported as the project's first finding: negative-result
contract-discipline-rules-9b3bae4c797f (hr-fd-1
9b3bae4c797f3358bed2412270bbdbe9b15adb83ef61132e11ff152122fa2979).
The claim: prose contract-discipline rules in RULES.md tax duration and
tokens across the board on a qwen3.8-27b omp stack and do not fix the
claimed-done failure mode. Registry seeding follows once private-pack
task ids are anonymized in the finding's split block (amendment
pending; the #7 replication amendment already establishes the
principle).

Three-cycle arc closed for this rule class: k=2 priced it twice, k=4
convicted it and revealed the screening gains as noise. The loop
worked exactly as designed at every stage.

## mut-contract-lean — 2026-08-27 — **REJECTED** (cycle 7 closes the rule class)

The leaner phrasing of cycle 6's contract discipline (verify against the
documented contract, distrust self-authored tests, no mandatory
checklist extraction). The hypothesis held where it was aimed: the
held-in tokens_in tax collapsed from +24 percent to +3.1 percent
(noise) and the 03 pass gain repeated at 2/2. The gate killed it one
floor over: held-out tokens_in_p50 rose 19.7 percent (1.15M to 1.37M),
and held-out is a floor. The rule taxes contract re-reading roughly
everywhere; held-in absorbed it this time, held-out did not. The target
task did not move in either cycle (16 at 0/2 both times).

Verdict on the class, not just the candidate: two phrasings of
RULES.md contract discipline are now priced at k=2, both rejected on
token floors, neither touching the pathology they were aimed at. The
class is dry; a third phrasing would be squeezing. The claimed-done
mechanism on 16 (circular self-validation) needs a different lever than
prose exhortation. Next distinct hypothesis on record: the 04
compaction-thrash sentinel evidence points at omp's context-management
config, a different surface entirely.

Cost note: both screening rejects together (2844s wall, 12.5M tokens_in)
cost less than ONE v6-era sweep. The cheap flow is why trying both
phrasings was affordable at all.

## mut-contract-checklist — 2026-08-26 — **REJECTED** (cycle 6, first run of the cheap flow)

Mutation: a RULES.md contract-checklist discipline (extract every
documented behavior into a checklist, verify item by item, never treat
self-authored tests as compliance evidence), motivated by the held-in
task 16's baseline pathology: in all four v7 rollouts the agent wrote
its own scratch tests, passed them, and declared done while 9-15 of the
24 hidden human tests failed. Circular self-validation, precisely the
failure the rule targeted.

Gate: REJECT at k=2 screening. The rule produced a real held-in pass
gain (03 went 2/2 against a 3/4 baseline floor) but taxed every task
with a 24 percent tokens_in_p50 regression (1.80M to 2.23M): the agent
re-reads contract material heavily, and the hard task did not move
(16 stayed 0/2). A discipline that raises the cost of every task
without cracking the one it was aimed at is a bad trade; the pawl
priced it correctly. Screening rejects are not claim-grade under the
#12 resolution; a k=4 re-proposal stays available if a cheaper phrasing
of the same discipline is found.

The operational headline: this was the first production run of the #12
flow, and every piece behaved. Cheap-first held-in-first order was
visible in the rollout sequence; the certainty conditions armed and
never fired (16's 0/4 baseline cannot regress); sentinels were skipped
with the skip recorded in the manifest; the manifest carries
screening_k, final_k, escalated, screening_verdict, concurrency, and
sweep_cost. The reject cost 1542s wall and 6.1M tokens_in against the
63 minutes and 15.3M a v6-era sweep paid: a 59 percent wall and 60
percent token saving on the first rejected candidate.

## Miner milestone met — 2026-08-26 — floors vintage 5, registry unblocked

Ten admitted tasks from four source repos: six private headroom tasks
in the bank and four public post-cutoff floors in the kit's new
floors/ pack (three from sqlglot, one from dspy, all MIT with license
files embedded, every target's last function-level change dated after
the subject model's 2026-08-14 release; floors/RECENCY.md carries the
table). Two rejects logged per the locked taxonomy: an excision-error
(identity comparisons defeat the comparison-flip auto-mutant) and a
preflight baseline-failure (sqlfluff's cwd-relative fixture glob). All
four floors re-audited independently after minting. The miner grew two
tested capabilities on the way: support modules and package-root
materialization with tests-tree verifiers. Issues #12 and #13 closed
the same day; stage-3 registry work (export and replicate) unblocks.

## baseline-v7 — 2026-08-26 — split v4 era floor, headroom restored

37/44 at k=4 over the nine bootstrap tasks plus private held-in tasks 10
and 16, recorded the same day the eval-cost resolution (#12) locked and
its implementation landed. Split v4 = v3 plus the deliberately hard
held-in task 16, minted from private production code precisely because
held-in had been 4/4 everywhere since baseline-v6 and the gate could not
reward pass gains. It worked: task 16 is 0/4, all four failures the
claimed-done mode (agent exits 0 with a partial implementation; 9-15 of
24 verifier tests fail), so pass-improving mutations are rewardable
again. 03 is 3/4 (its known unicode edge-case mode, agent exit 0, not
truncation). 09 recovered to 4/4.

Sentinel advisory, the loudest yet: 04 dropped to 2/4 with two 900s
rc-124 timeouts and p50 808s, against a same-morning v6 record of 4/4 at
226s p50 under byte-identical standing overlays. Stream forensics on the
first timeout show 61 turns, 60 tool executions, and 4 auto-compactions
with the agent still reasoning at the kill: an agent spiral with
compaction thrash, not machine contention (neighboring tasks sat exactly
on their v6 envelopes; no competing model load). 07 stayed clean at 4/4
in envelope. As sentinel evidence this is lawful mining material
(invariant 7): the compaction-thrash failure mode is a candidate
mutation target. Baselines record reality; the floor stands.

Sweep cost 6061s wall / 22.9M tokens_in at full k=4 with sentinels, the
price new baselines deliberately keep paying under #12; candidate
sweeps from here run the cheap flow (k=2 screening, early abort,
sentinels only on the promotion path).

## mut-maxtok-49k — 2026-08-26 — **REJECTED** (cycle 5, the lawful re-test)

maxTokens 32768->49152 through `ratchet click` (model-param op, fail-closed
selector, trap-restored), motivated by the private held-in task 10 — the
legitimate evidence path cycle 4 demanded. Gate: REJECT, one reason: no
held-in soft axis improved by >=15%. Held-in passed 4/4 everywhere in BOTH
arms, so there was no pass gain to reward.

The interesting part: the hypothesis is REAL but lives on the wrong side of
the split. Held-out 09 went 3/4 -> 4/4 under the raised cap, and one of its
rollouts emitted 40,840 output tokens — past the old cap, so the truncation
mechanism exists. Held-out gains deliberately never count (floor, not
target). Cycle 4 rejected this mutation for peeking at held-out evidence;
cycle 5 gave it the lawful test and the effect failed to appear where it
may be rewarded. The hypothesis is now settled, not shelved: the cap binds
rarely, on tasks the operator's own headroom does not currently reach.
Sentinel advisory: 04 and 07 each dropped one rollout (3/4 vs 4/4 floor);
watch for repeats.

First full cycle through the rewritten CLI end to end: sweep, era check,
structured op, gate, restore — one command, evidence on disk.

## baseline-v6 — 2026-08-26 — split v3 era floor, first sweep through the rewrite

39/40 at k=4 over the nine bootstrap tasks plus the private held-in task
10, recorded with `ratchet baseline sweep` (the rewritten runner's first
production sweep) and pinned with `baseline set-active` into the bank's
era registry. Standing-overlay hashes are byte-identical to the v5
registry: config ancestry unbroken across the rewrite. The one miss is
09 at 3/4 (its claimed-done headroom mode, up from 1/2 in v5). Task 10
passed 4/4 on its first agent attempts (75.5s p50), which makes the
cycle-5 maxTokens re-test a live question, not a formality. An earlier
sweep attempt was aborted and discarded when concurrent omp use shared
the GPU and inflated 04 to 788s; era floors are recorded on a quiet
machine or not at all.

## Bank created, era moves out, split v3 — 2026-08-26 (build step 3)

The personal bank exists (private repo, consumed via a local pack path;
docs refer to it as harness-bank). Era state now lives there: split v3 =
the disclosed split v2 below plus ONE re-minted private held-in task (the
long-implementation task unwound from this repo on 2026-08-25 for
privacy; re-mint #1 per the miner-milestone resolution — re-admitted with
numbers identical to the original mint: oracle triple green, 6/7 mutant
kills, stable 3/3). This repo's split.json stays as the disclosed v2
example. All v2-era labels (baseline-v5 and earlier) are incomparable to
v3-era gates; baseline-v6 (build step 4) opens the v3 era.

## mut-maxtok-48k — 2026-08-25 — **REJECTED** (cycle 4) — the pawl caught the operator

Mutation: maxTokens 32768→49152, targeting the stopReason=length truncation
failure mined from 09 r1. Sweep: 18/18 pass INCLUDING 09 at 2/2 with no
truncation — the targeted failure did not recur. Gate: REJECT anyway.

Reasons, and why they are correct:
- No held-in soft axis cleared the 15% effect threshold (all improved 10-14%
  — directionally positive, but a ceiling raise should mostly affect rare
  truncations; broad 10-14% swings are run variance, and the threshold
  treated them as such).
- The real win (09: 1/2→2/2) is on a HELD-OUT task, and held-out gains
  deliberately do not count as improvement — held-out is a floor, never a
  target. Which exposes the operator error: **the mutation was designed by
  mining a held-out failure.** That skirts the "held-out never shown to
  proposers" invariant, and the gate's structure made the peek unprofitable
  — exactly as designed.

Lessons codified:
1. Weakness mining draws specimens from held-in and sentinel runs ONLY
   (CONTEXT invariant 7, added this cycle).
2. The truncation-fix hypothesis stands observationally but needs a
   legitimate evidence path: mint a held-in task with the same
   long-implementation profile (bin/mine.py makes this cheap), then rerun —
   a real fix will show as held-in pass gain the gate can reward.

Cycle scorecard after 3 clicks: 1 PROMOTE (ctxslim, replicated), 2 REJECTS
(reason-effort: real trade-off; maxtok: illegitimate evidence path). The
pawl has now rejected a bad mutation, a noisy one, and an operator shortcut.


## mut-reason-med — 2026-08-25 — **REJECTED** by gate v1.2 (cycle 3, split v2 era)

Mutation: `reasoning_effort: medium` via models.yml extraBody (qwen3.8
template default is xhigh). Channel probed live pre-run. Full autonomous
cycle: baseline-v5 → mutate (trap-restored) → sweep → gate.

Gate reasons (REJECT):
- held_in pass regression: 03-js-slugify 2/2 → 1/2 — reduced reasoning
  measurably costs spec-following precision on the edge-case task
- soft-axis regressions on BOTH splits: duration and tokens_out UP (medium
  effort produced cheaper thinking but WORSE first attempts → more retry
  turns; tokens_out −62.8% held-in was the lone bright spot, swamped by
  held-out +24-40% regressions the v1.2 floor now catches — the exact gap
  the ctxslim promotion exposed, doing its job one cycle later)

Verdict: qwen3.8's default xhigh reasoning EARNS its cost in this harness.
Cheaper thinking is a false economy for agentic coding. Config restored
automatically; no harness change.

## baseline-v5 — 2026-08-25 — split v2 era floor

21/22 rollouts pass. Sentinel 04: **6/6 under modern config** (164-398s, no
timeouts) — closes gemini's k-bound ask; the pass-rate recovery is causal,
not luck. Task 09 (minted from production): **1/2 on its first agent
attempts** — r1 exhibited a NEW failure mode (ran 115s, exited cleanly,
never touched the excised stub: claimed-done-without-doing); r2 passed.
Real headroom from minted tasks on day one; next weakness-mining specimen.


## Attribution experiment VERDICT — 2026-08-24 — improvements CONFIRMED CAUSAL, credit reassigned

48 rollouts, per-task interleaved (same evening, same server), 3 arms × k=2:

| arm | pass | wall | tokens_in (sweep) | held-in tok_in p50 |
|---|---|---|---|---|
| exp-v4 (full current config) | 16/16 | 1,290s | 4.65M | 513K |
| exp-noslim (v4 infra, no overlay) | 16/16 | 1,316s | 4.82M | 670K |
| exp-v2replay (old runner, advisor on, in-repo) | **15/16** | **4,494s** | 7.77M | 1,264K |

Against the pre-registered criteria:

1. **Environment-drift hypothesis REFUTED.** The v2 replay reproduced the old
   numbers on the same evening — slower even than original v2 (4,494s vs
   3,496s) and reproduced the 04 timeout on demand, minutes after modern arms
   passed the same task. If anything the evening server was slower, making
   the modern numbers conservative.
2. **Wall-time win (−65%+) is caused by the infrastructure fixes**
   (isolation + advisor-off): replay 4,494s → noslim 1,316s; adding ctxslim
   changes wall by only ~2%.
3. **ctxslim's token claim REPLICATES**: held-in tokens_in 670K → 513K
   (−23.4%) in this independent paired run vs −25.1% in the original gated
   A/B. Two paired experiments, same effect size — solidly causal on its
   gated axis.
4. **The pass improvement is real and config-caused**: modern arms are 32/32
   today (04: 4/4) while the replay arm reproduced the timeout — the +1 task
   follows the config, not luck. (Gemini's k=10-on-04 remains open for
   tighter bounds; today's 04 record under modern config is 6/6.)

RESTORED HEADLINE (corrected attribution): one day, model frozen —
**−65% wall time and 15/16→16/16 from evaluation-infrastructure fixes
(isolation, advisor-off), −23-25% held-in input tokens from the gated
ctxslim mutation** — all now supported by same-day interleaved paired runs.
The reviewers' core objection (bundled ungated changes) was correct and is
resolved by measurement, not argument.


## Validity review of the one-day arc — 2026-08-24 — HEADLINE DOWNGRADED pending attribution

Triple adversarial review (codex PARTIALLY SUPPORTED / cursor PARTIALLY
SUPPORTED / gemini NOT SUPPORTED) of the v2→v4 claim. Consensus:

- The raw v4 run IS better than the raw v2 run; the tokens_in reduction has
  moderate-strong support (uniform across tasks, aligned with the gated
  ctxslim result).
- The CAUSAL headline ("−65% wall, +1 task from one day of ratcheting") is
  NOT yet supported: three ungated infrastructure changes (isolation,
  advisor-off, telemetry fix) are bundled into the comparison, v2 and v4 ran
  in different eras (midday vs evening, different server state), and 04's
  2/2 at k=2 is within its ~50% historical base rate ("first perfect sweep"
  may be luck).
- Methodology debts: manifests lack environment metadata (ts field now
  added), sequential-not-interleaved sweeps, sentinel 04 both outside the
  gate and central to the headline.

Until the attribution experiment reports, the claimable results are: the
gated ctxslim PROMOTE (−25.1% held-in tokens_in, paired conditions) and the
raw before/after observation (explicitly non-causal).

**Attribution experiment IN FLIGHT** (bin/exp-interleave.sh): per-task
interleaved 3 arms × k=2 — exp-v4 (current config), exp-noslim (v4 infra,
no overlay → isolates ctxslim), exp-v2replay (v2-era runner from git,
advisor on, in-repo workspaces → tests whether v2's numbers reproduce
today). Verdict criteria: if v2replay ≈ v4, the arc was environment drift;
if v2replay ≈ old v2 and noslim ≈ v4, infra changes dominate and ctxslim's
arc contribution is small; if noslim sits between v2replay and v4, both
contribute.

Also this cycle: task 09-proxy-concurrency-cap MINTED from production
vllm-proxy middleware (dispatch excised, existing pytest suite as hidden
oracle, auto-generated sabotage mutant) — oracle green all three directions,
REAP-stable 3/3. M4 pattern proven; not yet in the split.


## baseline-v4 — 2026-08-24 — **16/16, the new floor** (one day's arc complete)

Isolation-fixed runner (temp-dir workspaces, advisor-off eval config, absolute
telemetry paths) + promoted ctxslim overlay. This label is the comparison
baseline for all future candidates.

| task | pass | durations | tok_in p50 |
|---|---|---|---|
| 01-py-pagination | 2/2 | 13/17s | 100,487 |
| 02-py-config-type | 2/2 | 18/21s | 160,023 |
| 03-js-slugify | 2/2 | 57/67s | 190,132 |
| 04-sh-backup (sentinel) | **2/2 — first ever** | 167/422s | 777,127 |
| 05-py-dedupe | 2/2 | 21/26s | 180,697 |
| 06-py-version-sync | 2/2 | 18/25s | 159,005 |
| 07-py-lru-ttl (sentinel) | 2/2 | 98/106s | 287,204 |
| 08-py-report-bleed | 2/2 | 47/88s | 173,772 |

**The one-day arc (identical tasks, identical model, harness-only changes):**

| | pass | wall | tokens_in |
|---|---|---|---|
| baseline-v2 (omp defaults) | 15/16 | 3,496s | 6.19M |
| baseline-v3 (isolation+advisor-off) | 15/16 | 1,842s | (telemetry lost — path bug, superseded) |
| **baseline-v4** | **16/16** | **1,211s** | **4.06M** |

Net: **+1 task recovered, −65% wall time, −34% input tokens**, frozen model
throughout. Sources of the win: promoted ctxslim mutation (gated, −25%
held-in tokens), workspace isolation (no repo to scan or wander into),
advisor-off eval runs (no mid-run steering), each found by the loop's own
telemetry, canary, or mining.

Caveat kept honest: v3's telemetry loss was a self-inflicted runner bug
(streams redirected to /tmp), caught the same evening by the zero-token
anomaly. Durations across v3/v4 replicate, so the speed numbers stand.


## Weakness-mining pass 1 — 2026-08-24 — two infrastructure defects found

Mechanical stream profiling of the 04 timeouts (both eras), advisor-named:

1. **Workspace-isolation escape**: work dirs lived inside this repo; candidate
   04 r1 spent 130 turns (128 bash calls, 7.45M tokens in) wandering into
   `runs/` and reading its own live session stream, hard-looping on our
   infrastructure. FIXED: run.sh now executes agents in a temp dir outside the
   repo, archiving the workspace back post-run.
2. **Advisor interference in eval rollouts**: baseline 04 r2's transcript shows
   the agent responding to omp-advisor suggestions (incl. torture-test
   scripts) mid-eval — nondeterministic steering, a rigor amplifier on 04, and
   a role conflict with the advisor-as-veto-judge. FIXED: eval runs now always
   apply `mutations/eval-isolation.yml` (advisor.enabled: false) as
   infrastructure config.

Consequence: pre-fix and post-fix runs are NOT comparable. `baseline-v3`
(isolation-fixed runner + promoted ctxslim overlay) becomes the comparison
baseline for all future candidates. The 04 "rigor spiral" narrative is
partially revised: baseline r1 was genuine thoroughness; the candidate-era
7.45M-token blowup was the isolation bug, and the advisor amplified scope on
at least one rollout.

Also this cycle: simplicity-veto judge landed (bin/veto.py, advisory-only) —
first verdicts correctly discriminated the spiral rollout (OVER_ENGINEERED)
from clean ones (OK). Gate v1.2 adds the held-out soft-axis regression floor.


## mut-ctxslim-v1 — 2026-08-24 — **PROMOTED** (the first ratchet click)

Mutation: omp config overlay (`mutations/ctxslim-v1.yml`) disabling
skills/memories/autolearn for eval runs. Pre-flight probe: 34.5% system-prompt
cut (56,832 → 37,244 bytes). Gate v1.1 verdict vs pinned `baseline-v2`, k=2:

| gated axis (held-in aggregate) | baseline | candidate | delta |
|---|---|---|---|
| tokens_in_p50 | 1,072,572 | 803,637 | **−25.1%** (≥15% effect: PROMOTE driver) |
| duration_p50 | 446.5s | 419.5s | −6.0% (below effect threshold) |
| tokens_out_p50 | 21,110 | 20,928 | −0.9% |
| pass floors (held-in + held-out) | — | — | all held (15/16 rollouts pass, same as baseline) |

Manifest: `runs/mut-ctxslim-v1/manifest.json` (committed as evidence).
Operationally promoted: eval runs now use the overlay by default; the next
baseline label must be recorded WITH it.

Honest caveats (recorded, not hidden):

1. **Sentinel 04 drift**: its timeout rollout burned **7.45M tokens in** vs
   baseline's 0.9–1.5M — cheaper turns let the rigor spiral loop more inside
   the same 900s. The mutation makes the pathology hungrier, not better.
   Advisory only (sentinels never gate), and the strongest argument yet for
   the queued simplicity-veto work.
2. **Held-out 08 token increase** (median 321K → 487K): visible in evidence
   but NOT gated — gate v1.1's soft-axis regression floors cover held-in
   only. Gate v1.2 TODO: add a held-out soft-axis regression floor (held-out
   stays a floor, never an optimization target). The verdict stands per the
   rules pinned before the run; rules are never changed post-hoc to flip a
   verdict.


## baseline-v2 — 2026-08-24 — THE reference baseline (k=2, composite pass, tokens)

Runner v2: k=2 rollouts, composite pass (verifier AND rc==0), token telemetry
from omp --mode json. Harness: omp v18.0.4 defaults + thinking-on/temp-0.2
extraBody. Model: vllm/homelab-default (qwen38-27b-dflash2).

| task | role | pass | durations | tok_out p50 | tok_in p50 |
|---|---|---|---|---|---|
| 01-py-pagination | held-in | 2/2 | 46/58s | 1,453 | 165,174 |
| 02-py-config-type | held-out | 2/2 | 77/99s | 2,415 | 253,738 |
| 03-js-slugify | held-in | 2/2 | 120/245s | 10,745 | 318,226 |
| 04-sh-backup | sentinel | **1/2** | 676s / TIMEOUT 900s | 25,183 | 1,211,022 |
| 05-py-dedupe | held-in | 2/2 | 107/153s | 5,367 | 362,495 |
| 06-py-version-sync | held-in | 2/2 | 71/93s | 3,544 | 226,676 |
| 07-py-lru-ttl | sentinel | 2/2 | 142/196s | 9,627 | 234,313 |
| 08-py-report-bleed | held-out | 2/2 | 251/262s | 18,950 | 320,938 |

**15/16 rollouts pass · 3,496s wall · 154,573 tokens out · 6.19M tokens in.**

Findings:
1. The composite-pass rule caught its first real failure: 04 r1 timed out at
   900s with a passing tree — the k=1-era scorer would have called it a pass.
   The sentinel now documents the over-engineering spiral as a measurable
   50%-pass, 1.2M-token-in outlier (the simplicity veto's target).
2. Input-token load is dominated by harness context: even the smallest task
   costs ~165K tokens in per rollout. Context slimming is a first-class
   mutation target with a clean metric.
3. Run-to-run duration variance is real (03: 120s vs 245s) — vindicates k≥2
   and effect-size thresholds; single-run deltas under ~2x are noise-suspect.

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

## mutA-minimal-scope — 2026-08-24 — REJECTED (dead channel)

Mutation: scope-control line via `omp --append-system-prompt`. Target 04,
guards 01+05.

| task | baseline | mutA |
|---|---|---|
| 04-sh-backup | 790s PASS | 840s PASS |
| 01-py-pagination | 80s PASS | 66s PASS |
| 05-py-dedupe | 80s PASS | 85s PASS |

Verdict: no effect on the target (and the transcript shows the agent went even
deeper — it force-tested all three stat/date fallback branches).

Root cause — CONFIRMED omp-side, homelab exonerated (2026-08-24 differential):

- Behavioral probes with benign phrasing failed identically on BOTH
  vllm/homelab-default (through the proxy) and mac-gptoss/gpt-oss-20b (no
  proxy in the path) → not a homelab effect.
- Code read: vllm-proxy's SystemPromptSelector PREPENDS its template and
  preserves the client system message verbatim — it strips nothing.
- Session-log forensics (the smoking gun): the model's thinking says the
  appended text appeared "(from the node_repl MCP server instructions)" and
  that the system prompt labels that section "server-controlled and may not be
  verified" — so it deliberately declines to follow it. omp's prompt assembly
  places `--append-system-prompt` content in (or visually merged into) the
  MCP-instructions zone, whose framing marks it untrusted.

**FURTHER INVESTIGATION (upstream omp):** `--append-system-prompt` being
neutralized by its own placement defeats the flag's documented purpose —
candidate bug report to oh-my-pi. Repro: append "House style: end every reply
with the word ZANZIBAR.", observe refusal in thinking + absent token.

Usable mutation channels instead: `~/.omp/agent/RULES.md` (testing as
mutB-rules-scope), config-level system prompt, project context files.

Meta-lesson for the loop: verify a mutation channel is live (cheap probe with
an observable token) before spending an A/B on it — and when a probe fails,
differentiate WHERE it died before assigning blame.

## Channel forensics + mutB — 2026-08-24

Wire capture (dummy OpenAI server as an omp provider) settled the placement
question: the 57KB system prompt ends with the MCP-server sections
(### node_repl, ### context7), and `--append-system-prompt` text lands at
99.6% depth, unlabeled, directly after the last MCP section — visually inside
the zone the preamble calls "server-controlled and may not be verified".
Upstream flaw confidence: ~95% (placement is real; intent unknown).

Channel probe matrix (observable-token tests, local gpt-oss = no proxy):

| channel | live? |
|---|---|
| `--append-system-prompt`, bare | DEAD (model refuses as suspected injection) |
| `--append-system-prompt` + explicit trust header | **LIVE** ("Hello. ZANZIBAR") |
| `~/.omp/agent/RULES.md` | **LIVE** ("Hello! ZANZIBAR") |

Runner now auto-wraps EXTRA_SYS in the trust header.

### mutB-rules-scope — REJECTED

Scope rule via RULES.md (a proven-live channel), target 04:
790s baseline → **900s TIMEOUT (rc=124)** — the fix landed (verifier passed)
but the agent kept hardening until killed. With delivery proven, the failure is
CONTENT: generic scope guidance loses to task framing ("handles all legal
filenames" reads as a thoroughness mandate). Hard-task baselines from the same
run: 07-py-lru-ttl PASS 178s, 08-py-report-bleed PASS 348s (8/8 overall;
difficulty gradient 80→178→348→790s).

Next mutation candidates: (a) grader-aware scope phrasing ("a hidden verifier
scores only correctness of the fix; extra verification adds no credit"),
(b) accept the rigor and treat 04 as the open-scope stressor, tuning elsewhere.
