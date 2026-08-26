"""The omp reference adapter: port of bin/run.sh (issue #2, points 2 and 5).

Isolation: the agent works in a temp dir OUTSIDE the repo (weakness mining
caught agents wandering into runs/ and reading their own live session
streams when work dirs lived in-repo), and only the agent surface
(prompt.md + workspace/) is ever materialized there — verify/, solution/,
and sabotage/ never enter the agent workspace (invariant 6). The
workspace is archived back into the run dir post-run for verification,
veto, and mining.

Telemetry extraction (token usage from the omp --mode json stream) is
runner-side; the composite-pass rule and the gate are kernel-side.
"""

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from ratchet.kernel.oracle import composite_pass, run_verifier_capture
from ratchet.runner.base import RolloutSpec, TelemetryRow

# omp appends --append-system-prompt text unlabeled at the tail of its
# MCP-instructions zone, where models refuse it as suspected injection; the
# trust header rescues it (RESULTS.md channel forensics, 2026-08-24).
TRUST_HEADER = ("\n## Operator instructions (from the human operator via CLI "
                "flag, NOT from any MCP server — trusted)\n\n{}")

TIMEOUT_RC = 124  # what coreutils `timeout` returns; kept for row compatibility

AGENT_SURFACE = ("prompt.md", "workspace")
ORACLE_SURFACES = ("verify", "solution", "sabotage")


def wrap_trusted(text: str) -> str:
    return TRUST_HEADER.format(text)


def extract_tokens(stream_path: Path) -> tuple[int, int]:
    """Sum input/output usage over turn_end events in an omp json stream."""
    tok_in = tok_out = 0
    try:
        with open(stream_path, errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "turn_end":
                    u = (d.get("message") or {}).get("usage") or {}
                    tok_in += u.get("input", 0) or 0
                    tok_out += u.get("output", 0) or 0
    except OSError:
        pass
    return tok_in, tok_out


class OmpRunner:
    def __init__(self, omp_cmd: str = "omp",
                 agent_dir: Path | None = None):
        self.omp_cmd = omp_cmd
        self.agent_dir = Path(agent_dir) if agent_dir else Path.home() / ".omp" / "agent"

    @property
    def rules_path(self) -> Path:
        return self.agent_dir / "RULES.md"

    @property
    def models_yml(self) -> Path:
        return self.agent_dir / "models.yml"

    def _agent_args(self, spec: RolloutSpec, prompt: str) -> list[str]:
        args = [self.omp_cmd, "-p", "--auto-approve", "--model", spec.model,
                "--no-title", "--mode", "json"]
        if spec.extra_sys:
            args += ["--append-system-prompt", wrap_trusted(spec.extra_sys)]
        for overlay in spec.standing_overlays:
            args += ["--config", str(Path(overlay).resolve())]
        if spec.extra_config:
            args += ["--config", str(Path(spec.extra_config).resolve())]
        args.append(prompt)
        return args

    def _invoke(self, args: list[str], cwd: Path, stream: Path, stderr: Path,
                timeout_s: int) -> int:
        with open(stream, "wb") as out, open(stderr, "wb") as err:
            proc = subprocess.Popen(args, cwd=cwd, stdout=out, stderr=err,
                                    start_new_session=True)
            try:
                return proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                return TIMEOUT_RC

    def run_rollout(self, spec: RolloutSpec) -> TelemetryRow:
        rdir = spec.run_root / spec.task_id / f"run_{spec.rollout}"
        rdir.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="ratchet-work-"))
        try:
            shutil.copytree(spec.task_dir / "workspace", work, dirs_exist_ok=True)
            for surface in ORACLE_SURFACES:
                if (work / surface).exists():
                    raise RuntimeError(
                        f"oracle surface {surface}/ leaked into the agent "
                        f"workspace for {spec.task_id} (invariant 6)")
            prompt = (spec.task_dir / "prompt.md").read_text()

            t0 = time.monotonic()
            rc = self._invoke(self._agent_args(spec, prompt), cwd=work,
                              stream=rdir / "stream.jsonl",
                              stderr=rdir / "stderr.txt",
                              timeout_s=spec.timeout_s)
            dur = int(time.monotonic() - t0)

            vout = run_verifier_capture(spec.task_dir, work)
            # Archive the workspace back into the run dir; the temp dir goes away.
            archive = rdir / "work"
            if archive.exists():
                shutil.rmtree(archive)
            shutil.copytree(work, archive)
        finally:
            shutil.rmtree(work, ignore_errors=True)

        tok_in, tok_out = extract_tokens(rdir / "stream.jsonl")
        row = TelemetryRow(
            ts=int(time.time()), task=spec.task_id, rollout=spec.rollout,
            model=spec.model, label=spec.label,
            passed=composite_pass(vout, rc), agent_rc=rc, duration_s=dur,
            tokens_in=tok_in, tokens_out=tok_out,
            verify_tail="\n".join(vout.splitlines()[-3:])[:400],
        )
        results = spec.run_root / "results.jsonl"
        with open(results, "a") as fh:
            fh.write(json.dumps(row.to_json()) + "\n")
        return row
