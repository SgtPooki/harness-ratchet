"""The click verb: one mutation cycle with invariants 3/5/7 enforced
PRE-SWEEP, trap-restored ops, and the kernel gate deciding."""

import json
import os
import shutil
import stat

import pytest

from ratchet.cli import main
from ratchet.click import ClickError, ClickOp, check_motivation
from ratchet.config import CONFIG_ENV
from tests.test_runner import FAKE_OMP, STREAM

SPLIT = {"split_version": 3, "held_in": ["01-py-pagination"], "held_out": [],
         "sentinel": ["07-py-lru-ttl"]}


@pytest.fixture(autouse=True)
def no_ambient_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)


@pytest.fixture()
def bank(tmp_path, repo, monkeypatch):
    """A bank with a baseline recorded through the fake omp and a pinned era."""
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

    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    for task_id in SPLIT["held_in"] + SPLIT["sentinel"]:
        shutil.copytree(repo / "tasks" / task_id, bank / "tasks" / task_id,
                        ignore=shutil.ignore_patterns("__pycache__"))
    (bank / "era" / "split.json").write_text(json.dumps(SPLIT))

    agent = tmp_path / "home" / ".omp" / "agent"
    agent.mkdir(parents=True)
    (agent / "RULES.md").write_text("# Rules\n")
    (agent / "models.yml").write_text(
        "providers:\n  vllm:\n    models:\n"
        "      - id: homelab-default\n        maxTokens: 32768\n")

    cfgp = str(bank / "ratchet.toml")
    assert main(["baseline", "sweep", "base-v0", "--config", cfgp,
                 "--pack", str(bank / "tasks"), "--tasks", "all", "--k", "2"]) == 0
    assert main(["baseline", "set-active", "base-v0", "--config", cfgp]) == 0
    return bank


def cfgp(bank):
    return str(bank / "ratchet.toml")


def test_click_rules_full_cycle(bank, tmp_path, capsys):
    home_rules = tmp_path / "home" / ".omp" / "agent" / "RULES.md"
    before = home_rules.read_bytes()
    rc = main(["click", "cand-rules", "--config", cfgp(bank),
               "--op", "rules", "--text", "- prefer minimal diffs",
               "--motivated-by", "01-py-pagination", "--k", "2"])
    out = capsys.readouterr().out
    # identical fake-omp arms: REJECT (no axis improved), never an error
    assert rc == 1
    assert "GATE: REJECT" in out
    assert home_rules.read_bytes() == before  # trap-restored after the sweep

    run_root = bank / "runs" / "cand-rules"
    manifest = json.loads((run_root / "manifest.json").read_text())
    assert manifest["baseline"] == "base-v0" and manifest["split_version"] == 3
    op = json.loads((run_root / "op.json").read_text())
    assert op["declared_surface"] == "rules" and op["registry_admissible"] is True
    assert op["apply"]["vacuous"] is False
    # #12 decision 1: a reject never pays the sentinel bill; the manifest
    # says so explicitly instead of silently omitting the data
    assert manifest["sentinel_advisory"] == {"skipped": "rejected before sentinels"}
    assert manifest["screening_k"] == 2 and manifest["escalated"] is False
    assert manifest["sweep_cost"]["concurrency"] == 1


def test_click_model_param_prior_value_recorded(bank, tmp_path):
    models = tmp_path / "home" / ".omp" / "agent" / "models.yml"
    before = models.read_bytes()
    rc = main(["click", "cand-mp", "--config", cfgp(bank),
               "--op", "model-param", "--selector", "vllm/homelab-default:homelab-default",
               "--key", "maxTokens", "--value", "49152",
               "--motivated-by", "01-py-pagination", "--k", "2"])
    assert rc == 1
    assert models.read_bytes() == before
    op = json.loads((bank / "runs" / "cand-mp" / "op.json").read_text())
    assert op["apply"] == {"vacuous": False, "prior_value": "32768"}
    assert op["op"]["value"] == 49152


def test_click_sentinel_motivation_rejected_pre_sweep(bank, capsys):
    rc = main(["click", "cand-bad", "--config", cfgp(bank),
               "--op", "rules", "--text", "- x",
               "--motivated-by", "07-py-lru-ttl"])
    assert rc == 2
    assert "invariant 3" in capsys.readouterr().err
    assert not (bank / "runs" / "cand-bad").exists()  # no rollouts ran


def test_click_held_out_motivation_rejected(capsys):
    with pytest.raises(ClickError, match="invariant 7"):
        check_motivation({"held_in": [], "held_out": ["09-x"], "sentinel": []}, "09-x")


def test_click_mixed_op_flags_rejected(bank, capsys):
    rc = main(["click", "cand-mix", "--config", cfgp(bank),
               "--op", "rules", "--text", "- x", "--overlay", "some.yml",
               "--motivated-by", "01-py-pagination"])
    assert rc == 2
    assert "invariant 5" in capsys.readouterr().err


def test_click_vacuous_op_fails_fast(bank, capsys):
    rc = main(["click", "cand-vac", "--config", cfgp(bank),
               "--op", "model-param", "--selector", "vllm/homelab-default:homelab-default",
               "--key", "maxTokens", "--value", "32768",
               "--motivated-by", "01-py-pagination"])
    assert rc == 2
    assert "vacuous" in capsys.readouterr().err
    assert not (bank / "runs" / "cand-vac" / "results.jsonl").exists()


def test_click_immutable_candidate_label(bank, capsys):
    args = ["--config", cfgp(bank), "--op", "rules", "--text", "- x",
            "--motivated-by", "01-py-pagination", "--k", "2"]
    assert main(["click", "cand-dup", *args]) == 1
    assert main(["click", "cand-dup", *args]) == 2
    assert "immutable" in capsys.readouterr().err


def test_click_era_mismatch_exit_2(bank, capsys):
    split = json.loads((bank / "era" / "split.json").read_text())
    split["split_version"] = 4
    (bank / "era" / "split.json").write_text(json.dumps(split))
    rc = main(["click", "cand-era", "--config", cfgp(bank),
               "--op", "rules", "--text", "- x",
               "--motivated-by", "01-py-pagination"])
    assert rc == 2
    assert "era" in capsys.readouterr().err
