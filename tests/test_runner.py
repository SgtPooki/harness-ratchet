"""omp runner: isolation smoke test (the agent workspace never contains
oracle surfaces — issue #2 point 7), telemetry extraction, composite pass,
timeout semantics. Uses a fake `omp` on PATH; no model access needed."""

import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from ratchet.runner.base import RolloutSpec
from ratchet.runner.omp import OmpRunner, extract_tokens, wrap_trusted

STREAM = (
    '{"type":"turn_start"}\n'
    'not json at all\n'
    '{"type":"turn_end","message":{"usage":{"input":100,"output":10}}}\n'
    '{"type":"turn_end","message":{"usage":{"input":250,"output":40}}}\n'
    '{"type":"turn_end","message":{}}\n'
)

FAKE_OMP = """#!/bin/bash
# fake omp: records its cwd contents and args, emits a canned json stream.
set -u
ls -1A > "$FAKE_OMP_DIR/workspace-listing.txt"
pwd > "$FAKE_OMP_DIR/workspace-path.txt"
if [ -z "${FAKE_OMP_MUTE_ARGS:-}" ]; then printf '%s\\n---ARG---\\n' "$@"; fi
cat "$FAKE_OMP_STREAM"
cat "$HOME/.omp/agent/RULES.md" 2>/dev/null || true
if [ -n "${FAKE_OMP_SOLVE:-}" ]; then cp -R "$FAKE_OMP_SOLVE/." .; fi
if [ -n "${FAKE_OMP_SLEEP:-}" ]; then sleep "$FAKE_OMP_SLEEP"; fi
exit "${FAKE_OMP_RC:-0}"
"""


@pytest.fixture()
def fake_omp(tmp_path, monkeypatch):
    """Install a fake omp on PATH; returns its scratch dir for assertions."""
    scratch = tmp_path / "fake-omp"
    scratch.mkdir()
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    exe = bin_dir / "omp"
    exe.write_text(FAKE_OMP)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    stream = scratch / "canned-stream.jsonl"
    stream.write_text(STREAM)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_OMP_DIR", str(scratch))
    monkeypatch.setenv("FAKE_OMP_STREAM", str(stream))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return scratch


def spec_for(repo, tmp_path, task_id="01-py-pagination", **over):
    task_src = repo / "tasks" / task_id
    task_dir = tmp_path / "pack" / task_id
    if not task_dir.exists():
        shutil.copytree(task_src, task_dir,
                        ignore=shutil.ignore_patterns("__pycache__"))
    kw = dict(task_dir=task_dir, task_id=task_id, rollout=1, label="t-label",
              run_root=tmp_path / "runs" / "t-label", model="vllm/test-model",
              timeout_s=60)
    kw.update(over)
    return RolloutSpec(**kw)


def test_isolation_and_telemetry(repo, tmp_path, fake_omp):
    spec = spec_for(repo, tmp_path)
    row = OmpRunner().run_rollout(spec)

    # Isolation: the agent saw ONLY the agent surface, outside the repo.
    listing = set((fake_omp / "workspace-listing.txt").read_text().split())
    assert "paginate.py" in listing
    assert not listing & {"verify", "solution", "sabotage", "prompt.md"}
    work_path = (fake_omp / "workspace-path.txt").read_text().strip()
    assert "ratchet-work-" in work_path
    assert not Path(work_path).resolve().is_relative_to(repo)
    assert not Path(work_path).exists()  # temp dir cleaned up

    # Telemetry: canned usage summed; run artifacts archived.
    assert (row.tokens_in, row.tokens_out) == (350, 50)
    assert row.agent_rc == 0
    assert row.passed is False  # fake omp did not fix the workspace
    rdir = spec.run_root / spec.task_id / "run_1"
    assert (rdir / "stream.jsonl").is_file()
    assert (rdir / "work" / "paginate.py").is_file()
    rows = [json.loads(l) for l in
            (spec.run_root / "results.jsonl").read_text().splitlines()]
    assert rows[0]["pass"] is False and rows[0]["task"] == spec.task_id


def test_composite_pass_requires_rc_zero(repo, tmp_path, fake_omp, monkeypatch):
    spec = spec_for(repo, tmp_path)
    monkeypatch.setenv("FAKE_OMP_SOLVE", str(spec.task_dir / "solution"))
    row = OmpRunner().run_rollout(spec)
    assert row.passed is True and "PASS" in row.verify_tail

    monkeypatch.setenv("FAKE_OMP_RC", "3")
    row = OmpRunner().run_rollout(spec_for(repo, tmp_path, rollout=2))
    assert row.agent_rc == 3
    assert row.passed is False  # verifier PASS alone is not a pass (mutB lesson)


def test_timeout_rc_124(repo, tmp_path, fake_omp, monkeypatch):
    monkeypatch.setenv("FAKE_OMP_SLEEP", "30")
    row = OmpRunner().run_rollout(spec_for(repo, tmp_path, timeout_s=1))
    assert row.agent_rc == 124
    assert row.passed is False


def test_overlays_and_extra_sys_reach_argv(repo, tmp_path, fake_omp):
    overlay = tmp_path / "standing.yml"
    overlay.write_text("advisor:\n  enabled: false\n")
    mutation = tmp_path / "mut.yml"
    mutation.write_text("maxTokens: 49152\n")
    spec = spec_for(repo, tmp_path, standing_overlays=[overlay],
                    extra_config=mutation, extra_sys="scope tightly")
    OmpRunner().run_rollout(spec)
    stream = (spec.run_root / spec.task_id / "run_1" / "stream.jsonl").read_text()
    args = stream.split("---ARG---")[0:-1]
    joined = "\n".join(args)
    assert str(overlay.resolve()) in joined
    assert str(mutation.resolve()) in joined
    assert wrap_trusted("scope tightly") in joined  # trust header auto-wrap


def test_extract_tokens_golden(tmp_path):
    p = tmp_path / "stream.jsonl"
    p.write_text(STREAM)
    assert extract_tokens(p) == (350, 50)
    assert extract_tokens(tmp_path / "missing.jsonl") == (0, 0)
