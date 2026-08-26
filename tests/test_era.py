"""Era-registry behavior, ported exactly: mismatches are data errors
(exit 2 at the CLI boundary), never verdicts (issue #2, point 7)."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from ratchet.kernel.era import EraError, build_registry, check_era, load_registry
from ratchet.kernel.gate import GateDataError, write_manifest

ROWS = [{"task": "t1", "rollout": 1, "model": "vllm/homelab-default", "pass": True,
         "duration_s": 10, "tokens_in": 100, "tokens_out": 10}]
SPLIT = {"split_version": 2, "held_in": ["t1"], "held_out": [], "sentinel": []}


def registry(tmp_path, **over):
    cfg = tmp_path / "overlay.yml"
    if not cfg.exists():
        cfg.write_text("standing: overlay\n")
    reg = build_registry(label="base", results={"t1": ROWS}, split=SPLIT,
                         configs=["overlay.yml"], config_root=tmp_path,
                         set_at_commit="c" * 40, ts=1)
    reg.update(over)
    return reg


def check(reg, tmp_path, **over):
    kw = dict(baseline_label="base", split=SPLIT, base={"t1": ROWS},
              cand={"t1": ROWS}, config_root=tmp_path)
    kw.update(over)
    check_era(reg, **kw)


def test_clean_era_passes(tmp_path):
    check(registry(tmp_path), tmp_path)


@pytest.mark.parametrize("case,over,match", [
    ("wrong-baseline", {"baseline_label": "other"}, "not the active baseline"),
    ("split-bump", {"split": {**SPLIT, "split_version": 3}}, "era mismatch"),
    ("model-mix", {"cand": {"t1": [{**ROWS[0], "model": "other-model"}]}}, "model mismatch"),
])
def test_mismatches_raise(tmp_path, case, over, match):
    with pytest.raises(EraError, match=match):
        check(registry(tmp_path), tmp_path, **over)


def test_gate_version_change_raises(tmp_path):
    with pytest.raises(EraError, match="gate changed"):
        check(registry(tmp_path, gate_version=3), tmp_path)


def test_config_ancestry_raises(tmp_path):
    reg = registry(tmp_path)
    (tmp_path / "overlay.yml").write_text("standing: changed\n")
    with pytest.raises(EraError, match="config ancestry broken"):
        check(reg, tmp_path)


def test_missing_registry_raises(tmp_path):
    with pytest.raises(EraError, match="no .*ACTIVE_BASELINE"):
        load_registry(tmp_path / "runs" / "ACTIVE_BASELINE")


def test_mixed_model_baseline_refused(tmp_path):
    rows = {"t1": ROWS, "t2": [{**ROWS[0], "task": "t2", "model": "other"}]}
    with pytest.raises(EraError, match="mixes models"):
        build_registry(label="base", results=rows, split=SPLIT, configs=[],
                       config_root=tmp_path, set_at_commit="c" * 40, ts=1)


def test_manifest_immutability(tmp_path):
    p = tmp_path / "manifest.json"
    write_manifest(p, {"decision": "REJECT"})
    with pytest.raises(GateDataError, match="immutable"):
        write_manifest(p, {"decision": "PROMOTE"})


# --- the bin/gate.py wrapper must exit 2 on era mismatch, never 0/1 ---------

def load_wrapper():
    repo = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("gate_wrapper", repo / "bin" / "gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def scratch_repo(tmp_path):
    root = tmp_path / "repo"
    for label in ("base", "cand"):
        d = root / "runs" / label
        d.mkdir(parents=True)
        rows = [dict(ROWS[0], label=label, rollout=i) for i in (1, 2)]
        d.joinpath("results.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n")
    (root / "split.json").write_text(json.dumps(SPLIT))
    return root


def test_wrapper_exit_2_on_era_mismatch(tmp_path, monkeypatch, capsys):
    root = scratch_repo(tmp_path)
    reg = registry(root, label="some-other-baseline", config_sha256={})
    (root / "runs" / "ACTIVE_BASELINE").write_text(json.dumps(reg))
    wrapper = load_wrapper()
    monkeypatch.setattr(sys, "argv", ["gate.py", "base", "cand"])
    with pytest.raises(SystemExit) as exc:
        wrapper.main(root=root)
    assert exc.value.code == 2
    assert "era-registry check failed" in capsys.readouterr().err
    assert not (root / "runs" / "cand" / "manifest.json").exists()


def test_wrapper_exit_2_on_missing_results(tmp_path, monkeypatch, capsys):
    root = scratch_repo(tmp_path)
    shutil.rmtree(root / "runs" / "cand")
    (root / "runs" / "ACTIVE_BASELINE").write_text(json.dumps(registry(root, config_sha256={})))
    wrapper = load_wrapper()
    monkeypatch.setattr(sys, "argv", ["gate.py", "base", "cand"])
    with pytest.raises(SystemExit) as exc:
        wrapper.main(root=root)
    assert exc.value.code == 2


def test_wrapper_verdict_on_clean_era(tmp_path, monkeypatch):
    root = scratch_repo(tmp_path)
    (root / "runs" / "ACTIVE_BASELINE").write_text(json.dumps(registry(root, config_sha256={})))
    wrapper = load_wrapper()
    monkeypatch.setattr(wrapper, "head_commit", lambda _root: "d" * 40)
    monkeypatch.setattr(sys, "argv", ["gate.py", "base", "cand"])
    with pytest.raises(SystemExit) as exc:
        wrapper.main(root=root)
    # identical arms: REJECT (no axis improved), exit 1, manifest written once
    assert exc.value.code == 1
    manifest = json.loads((root / "runs" / "cand" / "manifest.json").read_text())
    assert manifest["decision"] == "REJECT"
    assert manifest["rollback_target"] == "d" * 40
