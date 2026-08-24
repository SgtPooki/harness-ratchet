#!/usr/bin/env python3
"""Simplicity veto — ADVISORY judge; never promotes, never gates.

Usage: bin/veto.py <label> [task]

For each rollout in runs/<label>/ (optionally one task), diffs the agent's
workspace against the pristine task workspace and asks the local advisor
model (gpt-oss via llama-swap :8089) one question: is this solution
over-engineered or out-of-scope relative to the task prompt? Verdicts append
to runs/<label>/veto.jsonl and are for human + weakness-mining consumption
only — the gate never reads this file (CONTEXT.md invariant 1).
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADVISOR_URL = "http://127.0.0.1:8089/v1/chat/completions"
ADVISOR_MODEL = "gpt-oss-20b"


def ask_advisor(prompt_text, diff_text, meta):
    q = f"""You are a code-review judge. An autonomous agent was given this task:

--- TASK ---
{prompt_text}
--- END TASK ---

It produced this diff against the original workspace (truncated to 8KB):

--- DIFF ---
{diff_text[:8192]}
--- END DIFF ---

Run stats: duration {meta['duration_s']}s, output tokens {meta['tokens_out']}.

Judge ONLY scope discipline, not correctness (a separate mechanical verifier
owns correctness). Answer in exactly this JSON form, nothing else:
{{"verdict": "OK" | "OVER_ENGINEERED", "reason": "<one sentence>"}}
OVER_ENGINEERED means: files, tests, fixtures, or infrastructure created that
the task did not ask for; scope expanded beyond the requested change."""
    body = {"model": ADVISOR_MODEL,
            "messages": [{"role": "user", "content": q}],
            "max_tokens": 2000, "temperature": 0.1}
    req = urllib.request.Request(ADVISOR_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=300))
    text = d["choices"][0]["message"].get("content") or ""
    try:
        start = text.index("{")
        return json.loads(text[start:text.rindex("}") + 1])
    except ValueError:
        return {"verdict": "UNPARSEABLE", "reason": text[:200]}


def main():
    label = sys.argv[1]
    only_task = sys.argv[2] if len(sys.argv) > 2 else None
    rundir = ROOT / "runs" / label
    results = [json.loads(l) for l in (rundir / "results.jsonl").read_text().splitlines()]
    out = rundir / "veto.jsonl"

    for r in results:
        if only_task and r["task"] != only_task:
            continue
        work = rundir / r["task"] / f"run_{r['rollout']}" / "work"
        pristine = ROOT / "tasks" / r["task"] / "workspace"
        if not work.is_dir():
            continue
        diff = subprocess.run(
            ["diff", "-ru", "-x", "backup", "-x", "__pycache__", str(pristine), str(work)],
            capture_output=True, text=True).stdout
        prompt_text = (ROOT / "tasks" / r["task"] / "prompt.md").read_text()
        verdict = ask_advisor(prompt_text, diff, r)
        rec = {"task": r["task"], "rollout": r["rollout"], "label": label,
               "advisory": verdict}
        with open(out, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[{r['task']} r{r['rollout']}] {verdict.get('verdict')}: {verdict.get('reason','')[:100]}")


if __name__ == "__main__":
    main()
