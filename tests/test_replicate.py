"""The replicate verb: finding verification, lane determination, stage-A
pin checks, and the transfer-lane run with its four outcomes."""

import json
from pathlib import Path

import pytest

from ratchet.click import ClickOp, run_click
from ratchet.config import RatchetConfig
from ratchet.export import export_finding
from ratchet.kernel.era import build_registry
from ratchet.kernel.gate import load_results
from ratchet.kernel.schemas import validation_errors
from ratchet.replicate import (ReplicateError, determine_lane, load_finding,
                               replicate_transfer, stage_a_exact,
                               write_mismatch)
from tests.test_click_screening import ScriptedRunner

SPLIT = {"split_version": 9, "held_in": ["hi-a", "hi-b"],
         "held_out": ["ho-a"], "sentinel": []}
TASKS = SPLIT["held_in"] + SPLIT["held_out"]

FP = {"algorithm": "hr-mf-1", "weights": "sha256:" + "e" * 64,
      "family": "qwen3-27b", "family_source": "operator"}
ENV = {"engine": "vllm", "engine_version": "nightly", "quantization": "none",
       "context_window": 122880, "max_tokens": 32768,
       "sampling": {"temperature": 0.2}}


def base_row(task, i, label="b0", passed=True):
    return {"ts": 0, "task": task, "rollout": i, "model": "m", "label": label,
            "pass": passed, "agent_rc": 0, "duration_s": 10, "tokens_in": 100,
            "tokens_out": 50, "verify_tail": ""}


def make_bank(root: Path, *, private_bank: bool) -> RatchetConfig:
    (root / "era").mkdir(parents=True)
    (root / "runs").mkdir()
    pack = root / "tasks"
    pack.mkdir()
    for t in TASKS:
        (pack / t).mkdir()
    (pack / "pack.json").write_text(json.dumps(
        {"format_version": 1, "name": root.name, "digest": "2" * 64,
         "digest_algorithm": "hr-pd-1",
         "vintage": {"number": 1, "date": "2026-08-26"}, "tasks": TASKS}))
    cfg = RatchetConfig(path=root / "ratchet.toml", runs_dir=root / "runs",
                        era_dir=root / "era",
                        bootstrap_pack=pack if not private_bank else root / "nowhere",
                        bank_pack=pack if private_bank else root / "nowhere",
                        harness="omp", model="m", timeout_s=60, k=2,
                        standing_overlays=[])
    cfg.split_file.write_text(json.dumps(SPLIT))
    rows = [base_row(t, i) for t in TASKS for i in range(1, 5)]
    (root / "runs" / "b0").mkdir()
    (root / "runs" / "b0" / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows))
    reg = build_registry(label="b0", results=load_results(
        root / "runs" / "b0" / "results.jsonl"), split=SPLIT, configs=[],
        config_root=root, set_at_commit="a" * 40, ts=0)
    cfg.active_baseline.write_text(json.dumps(reg))
    (root / "era" / "model-fingerprint.json").write_text(json.dumps(FP))
    (root / "era" / "engine-envelope.json").write_text(json.dumps(
        {"harness_version": "omp 18", "runtime_envelope": dict(ENV)}))
    return cfg


class OpRunner(ScriptedRunner):
    """ScriptedRunner plus the surface attributes build_op needs."""

    def __init__(self, script, tmp: Path):
        super().__init__(script)
        agent = tmp / "agent"
        agent.mkdir(parents=True, exist_ok=True)
        self.rules_path = agent / "RULES.md"
        self.rules_path.write_text("# rules\n")
        self.models_yml = agent / "models.yml"
        self.models_yml.write_text(
            "providers:\n  vllm:\n    models:\n"
            "      - id: x\n        maxTokens: 32768\n")


@pytest.fixture()
def finding(tmp_path):
    """A real exported finding from a submitter bank."""
    cfg = make_bank(tmp_path / "submitter", private_bank=False)
    probes = cfg.runs_dir / "probes"
    probes.mkdir()
    (probes / "2026-08-26-rules.json").write_text(json.dumps(
        {"method": "observable-token", "observed": True, "date": "2026-08-26"}))
    runner = OpRunner({}, tmp_path / "sub-omp")
    manifest, code = run_click(cfg, candidate="cand",
                               op=ClickOp(kind="rules",
                                          payload={"text": "- be terse"}),
                               motivated_by="hi-a", k=4, runner=runner)
    # identical scripted arms REJECT; a negative-result finding is fine
    out = export_finding(cfg, candidate="cand", slug="terse-rule",
                         kind="negative-result", submitter="github:sub",
                         out_root=cfg.root / "findings")
    return out


def test_load_finding_verifies_digest(finding):
    doc = load_finding(finding)
    assert doc["slug"] == "terse-rule"
    tampered = finding / "evidence" / "extra.txt"
    tampered.write_text("x")
    with pytest.raises(ReplicateError, match="does not recompute"):
        load_finding(finding)


def test_lane_determination(finding):
    doc = load_finding(finding)
    # concurrency 1 matches the claim's manifest-recorded concurrency
    lane, _ = determine_lane(doc, FP, {**ENV, "concurrency": 1})
    assert lane == "exact"
    lane, reasons = determine_lane(
        doc, {**FP, "weights": "sha256:" + "f" * 64},
        {**ENV, "concurrency": 1})
    assert lane == "local-transfer"
    assert any("weights" in r for r in reasons)


def test_stage_a_private_pack_is_mismatch(tmp_path, finding):
    doc = load_finding(finding)
    doc["claim"]["packs"][0]["private"] = True
    cfg = make_bank(tmp_path / "replicator", private_bank=True)
    reasons = stage_a_exact(doc, cfg)
    assert any("private" in r for r in reasons)


def test_write_mismatch_manifest_validates(tmp_path, finding):
    doc = load_finding(finding)
    cfg = make_bank(tmp_path / "replicator", private_bank=True)
    path = write_mismatch(cfg, doc, submitter="github:rep",
                          out_root=cfg.root / "replications",
                          reasons=["pack unobtainable"])
    rep = json.loads((path / "replication.json").read_text())
    assert rep["outcome"] == "environment-mismatch"
    assert validation_errors("replication", rep) == []


def test_transfer_refuted_and_anonymized(tmp_path, finding):
    doc = load_finding(finding)
    cfg = make_bank(tmp_path / "replicator", private_bank=True)
    runner = OpRunner({}, tmp_path / "rep-omp")  # identical arms -> REJECT
    path, outcome = replicate_transfer(cfg, doc, submitter="github:rep",
                                       out_root=cfg.root / "replications",
                                       runner=runner)
    assert outcome == "refuted"
    rep = json.loads((path / "replication.json").read_text())
    assert rep["lane"] == "local-transfer"
    assert validation_errors("replication", rep) == []
    # a refuted transfer is a gate REJECT even though the arms tied (#7:
    # the mutation did not help this stack)
    assert set(rep["task_anonymization"]) == {"t1", "t2", "t3"}
    # private bank ids never appear in the shipped evidence
    ev = (path / "evidence" / "candidate.results.jsonl").read_text()
    assert "hi-a" not in ev and "t1" in ev


def test_transfer_replicated_on_faster_arms(tmp_path, finding):
    doc = load_finding(finding)
    cfg = make_bank(tmp_path / "replicator", private_bank=True)
    script = {(t, i): {"duration_s": 2} for t in TASKS for i in range(1, 5)}
    runner = OpRunner(script, tmp_path / "rep-omp")
    path, outcome = replicate_transfer(cfg, doc, submitter="github:rep",
                                       out_root=cfg.root / "replications",
                                       runner=runner)
    assert outcome == "replicated"


def test_transfer_vacuous_from_apply_flag(tmp_path, finding):
    doc = load_finding(finding)
    # a model-param op already at the payload value applies vacuously
    doc["operations"] = [{"kind": "model-param",
                          "payload": {"omp_model_alias": "vllm/x", "yaml_id": "x",
                                      "key": "maxTokens", "value": 32768}}]
    doc["declared_surface"] = "model-param"
    cfg = make_bank(tmp_path / "replicator", private_bank=True)
    runner = OpRunner({}, tmp_path / "rep-omp")
    path, outcome = replicate_transfer(cfg, doc, submitter="github:rep",
                                       out_root=cfg.root / "replications",
                                       runner=runner)
    assert outcome == "vacuous"
    rep = json.loads((path / "replication.json").read_text())
    assert rep["op_application"]["vacuous"] is True
    assert runner.calls == []  # the gate is skipped; no rollouts ran
