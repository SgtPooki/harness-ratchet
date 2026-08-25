# Results ledger

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
