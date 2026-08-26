"""The export verb: finding assembly per #5 (amended), with every locked
refusal exercised."""

import json
from pathlib import Path

import pytest

from ratchet.config import RatchetConfig
from ratchet.export import ExportError, export_finding
from ratchet.kernel.digests import finding_digest
from ratchet.kernel.era import build_registry
from ratchet.kernel.gate import load_results
from ratchet.kernel.schemas import validation_errors

SPLIT = {"split_version": 9, "held_in": ["t-a"], "held_out": ["t-b"],
         "sentinel": ["t-s"]}
TASKS = ["t-a", "t-b", "t-s"]


def row(task, i, label, passed=True):
    return {"ts": 0, "task": task, "rollout": i, "model": "m", "label": label,
            "pass": passed, "agent_rc": 0, "duration_s": 10, "tokens_in": 100,
            "tokens_out": 50,
            "verify_tail": f"detail line\nPASS {Path.home()}/secret/x"}


@pytest.fixture()
def cfg(tmp_path):
    root = tmp_path / "bank"
    (root / "era").mkdir(parents=True)
    (root / "runs").mkdir()
    pack = root / "tasks"
    pack.mkdir()
    for t in TASKS:
        (pack / t).mkdir()
    (pack / "pack.json").write_text(json.dumps(
        {"format_version": 1, "name": "bank", "digest": "0" * 64,
         "digest_algorithm": "hr-pd-1",
         "vintage": {"number": 1, "date": "2026-08-26"}, "tasks": TASKS}))
    c = RatchetConfig(path=root / "ratchet.toml", runs_dir=root / "runs",
                      era_dir=root / "era", bootstrap_pack=pack,
                      bank_pack=pack, harness="omp", model="vllm/x",
                      timeout_s=60, k=2, standing_overlays=[])
    c.split_file.write_text(json.dumps(SPLIT))

    for label in ("b0", "cand"):
        d = root / "runs" / label
        d.mkdir()
        rows = [row(t, i, label) for t in TASKS for i in range(1, 5)]
        (d / "results.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows))
    reg = build_registry(label="b0", results=load_results(
        root / "runs" / "b0" / "results.jsonl"), split=SPLIT, configs=[],
        config_root=root, set_at_commit="a" * 40, ts=0)
    c.active_baseline.write_text(json.dumps(reg))

    manifest = {"gate_version": 4, "split_version": 9, "baseline": "b0",
                "candidate": "cand", "min_k": 2, "effect_threshold": 0.15,
                "decision": "PROMOTE", "reasons": [],
                "improved_axes": ["tokens_in_p50"], "evidence": {},
                "sentinel_advisory": {}, "rollback_target": "b" * 40,
                "screening_k": 2, "final_k": 4, "escalated": True,
                "screening_verdict": "PROMOTE", "aborted_at": None,
                "abort_condition": None, "concurrency": 1,
                "sweep_cost": {"elapsed_wall_s": 100}}
    (root / "runs" / "cand" / "manifest.json").write_text(json.dumps(manifest))
    op = {"candidate": "cand",
          "op": {"kind": "model-param", "omp_model_alias": "vllm/x",
                 "yaml_id": "x", "key": "maxTokens", "value": 49152},
          "op_digest12": "d" * 12, "motivated_by": "t-a",
          "declared_surface": "model-param", "registry_admissible": True,
          "apply": {"vacuous": False, "prior_value": "32768"},
          "k": 4, "min_k": 2, "effect_threshold": 0.15}
    (root / "runs" / "cand" / "op.json").write_text(json.dumps(op))

    (root / "era" / "model-fingerprint.json").write_text(json.dumps(
        {"algorithm": "hr-mf-1", "weights": "sha256:" + "e" * 64,
         "family": "qwen3-27b", "family_source": "operator",
         "provenance": {"source": "hf", "repo": "org/m", "quant": "gptq-w4a16"}}))
    (root / "era" / "engine-envelope.json").write_text(json.dumps(
        {"harness_version": "omp 18",
         "runtime_envelope": {"engine": "vllm", "engine_version": "nightly",
                              "quantization": "none", "context_window": 122880,
                              "max_tokens": 32768,
                              "sampling": {"temperature": 0.2}}}))
    return c


def do_export(c, **kw):
    args = dict(candidate="cand", slug="maxtok-49k", kind="improvement",
                submitter="github:tester", out_root=c.root / "findings")
    args.update(kw)
    return export_finding(c, **args)


def test_export_happy_path(cfg, capsys):
    out = do_export(cfg)
    doc = json.loads((out / "finding.json").read_text())
    assert out.name == f"maxtok-49k-{doc['digest'][:12]}"
    # the digest recomputes over the directory with the self-ref rule
    assert finding_digest(out) == doc["digest"]
    # fully schema-valid including the digest
    assert validation_errors("finding", doc) == []
    assert doc["claim"]["k"] == 4 and doc["claim"]["decision"] == "PROMOTE"
    assert doc["claim"]["channel_liveness"]["not_required"]
    # evidence rows: verify_tail capped to the last line and home redacted
    rows = [json.loads(l) for l in
            (out / "evidence" / "candidate.results.jsonl").read_text().splitlines()]
    assert all("\n" not in r["verify_tail"] for r in rows)
    assert all(str(Path.home()) not in r["verify_tail"] for r in rows)
    assert (out / "mutation" / "model-param.json").is_file()
    assert "DISCLOSES split" in capsys.readouterr().out


def test_export_refuses_screening_k(cfg):
    m = cfg.runs_dir / "cand" / "manifest.json"
    doc = json.loads(m.read_text())
    doc["final_k"] = 2
    m.write_text(json.dumps(doc))
    with pytest.raises(ExportError, match="not claim-grade"):
        do_export(cfg)


def test_export_refuses_mixed_packs(cfg, tmp_path):
    other = tmp_path / "otherpack"
    (other / "t-b").mkdir(parents=True)
    (other / "pack.json").write_text(json.dumps(
        {"format_version": 1, "name": "floors", "digest": "1" * 64,
         "digest_algorithm": "hr-pd-1",
         "vintage": {"number": 1, "date": "2026-08-26"}, "tasks": ["t-b"]}))
    (Path(cfg.bank_pack) / "t-b").rmdir()
    pj = Path(cfg.bank_pack) / "pack.json"
    d = json.loads(pj.read_text())
    d["tasks"] = ["t-a", "t-s"]
    pj.write_text(json.dumps(d))
    cfg.bootstrap_pack = other
    with pytest.raises(ExportError, match="more than one pack"):
        do_export(cfg)


def test_export_refuses_inadmissible_channel(cfg):
    p = cfg.runs_dir / "cand" / "op.json"
    doc = json.loads(p.read_text())
    doc["registry_admissible"] = False
    p.write_text(json.dumps(doc))
    with pytest.raises(ExportError, match="inadmissible"):
        do_export(cfg)


def test_export_fails_closed_without_fingerprint(cfg):
    (cfg.era_dir / "model-fingerprint.json").unlink()
    with pytest.raises(ExportError, match="model-fingerprint.json"):
        do_export(cfg)


def test_export_kind_decision_mismatch(cfg):
    with pytest.raises(ExportError, match="requires a REJECT"):
        do_export(cfg, kind="negative-result")
