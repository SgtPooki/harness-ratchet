"""The #12 sweep flow inside click: screening at k=2, escalation on a
screening PROMOTE, early abort on certainty, sentinel skip on rejects,
ordering, and the recorded cost/verdict bookkeeping. Uses a synthetic
runner so both arms' telemetry is fully controlled."""

import json
from pathlib import Path

import pytest

from ratchet.click import ClickOp, run_click, sweep_order
from ratchet.config import RatchetConfig
from ratchet.kernel.era import build_registry
from ratchet.runner.base import RolloutSpec, TelemetryRow

SPLIT = {"split_version": 9, "held_in": ["hi-slow", "hi-fast"],
         "held_out": ["ho-a"], "sentinel": ["sent-a"]}
TASKS = SPLIT["held_in"] + SPLIT["held_out"] + SPLIT["sentinel"]


class ScriptedRunner:
    """Telemetry per (task, rollout) from a script; appends rows like the
    real runner so the gate can load them back from disk."""

    def __init__(self, script):
        self.script = script          # (task_id, i) -> dict overrides
        self.calls = []

    def run_rollout(self, spec: RolloutSpec) -> TelemetryRow:
        self.calls.append((spec.task_id, spec.rollout))
        over = self.script.get((spec.task_id, spec.rollout), {})
        # default telemetry mirrors the baseline exactly (identical arms)
        base_duration = 90 if spec.task_id == "hi-slow" else 10
        row = TelemetryRow(
            ts=0, task=spec.task_id, rollout=spec.rollout, model=spec.model,
            label=spec.label, passed=over.get("pass", True), agent_rc=0,
            duration_s=over.get("duration_s", base_duration),
            tokens_in=over.get("tokens_in", 100),
            tokens_out=over.get("tokens_out", 50), verify_tail="")
        with open(spec.run_root / "results.jsonl", "a") as fh:
            fh.write(json.dumps(row.to_json()) + "\n")
        return row


def base_row(task, i, *, passed=True, duration_s=10):
    return {"ts": 0, "task": task, "rollout": i, "model": "m", "label": "b0",
            "pass": passed, "agent_rc": 0, "duration_s": duration_s,
            "tokens_in": 100, "tokens_out": 50, "verify_tail": ""}


@pytest.fixture()
def cfg(tmp_path):
    root = tmp_path / "bank"
    (root / "era").mkdir(parents=True)
    (root / "runs" / "b0").mkdir(parents=True)
    (root / "tasks").mkdir()
    for t in TASKS:
        (root / "tasks" / t).mkdir()
    c = RatchetConfig(path=root / "ratchet.toml", runs_dir=root / "runs",
                      era_dir=root / "era", bootstrap_pack=root / "tasks",
                      bank_pack=root / "tasks", harness="omp", model="m",
                      timeout_s=60, k=2, standing_overlays=[])
    c.split_file.write_text(json.dumps(SPLIT))
    # baseline: everything passes at k=4; hi-slow slower than hi-fast
    rows = []
    for t in TASKS:
        for i in range(1, 5):
            rows.append(base_row(t, i, duration_s=90 if t == "hi-slow" else 10))
    (root / "runs" / "b0" / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    from ratchet.kernel.gate import load_results
    reg = build_registry(label="b0",
                         results=load_results(root / "runs" / "b0" / "results.jsonl"),
                         split=SPLIT, configs=[], config_root=root,
                         set_at_commit="deadbeef", ts=0)
    c.active_baseline.write_text(json.dumps(reg))
    return c


OP = ClickOp(kind="append-system-prompt", payload={"text": "probe"})


def click(cfg, runner, candidate, **kw):
    return run_click(cfg, candidate=candidate, op=OP,
                     motivated_by="hi-fast", runner=runner, **kw)


def test_order_held_in_first_cheap_first(cfg):
    base = {t: [base_row(t, i, duration_s=90 if t == "hi-slow" else 10)
                for i in range(1, 5)] for t in TASKS}
    assert sweep_order(SPLIT, base) == ["hi-fast", "hi-slow", "ho-a"]


def test_screening_reject_skips_sentinels_and_records(cfg, capsys):
    runner = ScriptedRunner({})   # identical arms -> no axis improves
    manifest, code = click(cfg, runner, "cand-screen")
    assert code == 1 and manifest["decision"] == "REJECT"
    assert manifest["screening_k"] == 2 and manifest["final_k"] == 2
    assert manifest["escalated"] is False
    assert manifest["screening_verdict"] == "REJECT"
    assert manifest["sentinel_advisory"] == {"skipped": "rejected before sentinels"}
    assert all(t != "sent-a" for t, _ in runner.calls)
    cost = manifest["sweep_cost"]
    assert cost["rollouts_run"] == 6 and cost["rollouts_planned"] == 6
    assert cost["aborted"] is False and cost["concurrency"] == 1
    # held-in 100% notice printed, informational only
    assert "no pass gain is available" in capsys.readouterr().out


def test_early_abort_on_first_certain_failure(cfg):
    # hi-fast (first in order) fails rollout 1 against a 4/4 baseline:
    # certain regardless of everything else
    runner = ScriptedRunner({("hi-fast", 1): {"pass": False}})
    manifest, code = click(cfg, runner, "cand-abort")
    assert code == 1 and manifest["decision"] == "REJECT"
    assert runner.calls == [("hi-fast", 1)]
    assert manifest["aborted_at"] == 1
    assert "hi-fast" in manifest["abort_condition"]
    assert manifest["sweep_cost"]["aborted"] is True
    assert manifest["sentinel_advisory"]["skipped"] == manifest["abort_condition"]


def test_screening_promote_escalates_and_runs_sentinels(cfg):
    # candidate is uniformly much faster: every stage promotes
    script = {(t, i): {"duration_s": 2} for t in TASKS for i in range(1, 5)}
    runner = ScriptedRunner(script)
    manifest, code = click(cfg, runner, "cand-fast")
    assert code == 0 and manifest["decision"] == "PROMOTE"
    assert manifest["escalated"] is True
    assert manifest["screening_k"] == 2 and manifest["final_k"] == 4
    assert manifest["screening_verdict"] == "PROMOTE"
    # gated tasks reached k=4, sentinels ran at final k
    gated_counts = {t: sum(1 for c in runner.calls if c[0] == t)
                    for t in SPLIT["held_in"] + SPLIT["held_out"]}
    assert set(gated_counts.values()) == {4}
    assert sum(1 for c in runner.calls if c[0] == "sent-a") == 4
    assert "sent-a" in manifest["sentinel_advisory"]
    assert manifest["sweep_cost"]["rollouts_run"] == 16


def test_screening_promote_dies_at_k4(cfg):
    # fast for the first two rollouts, slow enough after that the k=4
    # median of [2, 2, x, x] lands exactly back on the baseline median:
    # k=2 clears the 15% bar, k=4 shows no improvement at all
    script = {(t, i): {"duration_s": 2} for t in TASKS for i in (1, 2)}
    script.update({(t, i): {"duration_s": 178 if t == "hi-slow" else 18}
                   for t in TASKS for i in (3, 4)})
    runner = ScriptedRunner(script)
    manifest, code = click(cfg, runner, "cand-mirage")
    assert code == 1 and manifest["decision"] == "REJECT"
    assert manifest["escalated"] is True and manifest["final_k"] == 4
    assert manifest["screening_verdict"] == "PROMOTE"
    assert manifest["sentinel_advisory"] == {"skipped": "rejected before sentinels"}


def test_explicit_k4_skips_screening_stage(cfg):
    script = {(t, i): {"duration_s": 2} for t in TASKS for i in range(1, 5)}
    runner = ScriptedRunner(script)
    manifest, code = click(cfg, runner, "cand-k4", k=4)
    assert code == 0
    assert manifest["screening_k"] == 4 and manifest["final_k"] == 4
    assert manifest["escalated"] is False


def test_concurrency_mismatch_refused_pre_sweep(cfg):
    reg = json.loads(cfg.active_baseline.read_text())
    reg["concurrency"] = 8
    cfg.active_baseline.write_text(json.dumps(reg))
    runner = ScriptedRunner({})
    from ratchet.click import ClickError
    with pytest.raises(ClickError, match="envelope mismatch"):
        click(cfg, runner, "cand-env")
    assert runner.calls == []
