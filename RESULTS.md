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
