"""CLI step-2 verbs: init scaffolding, baseline sweep + set-active through a
fake omp, probe liveness through the rules channel."""

import json
import os
import stat

import pytest

from ratchet.cli import main
from ratchet.config import CONFIG_ENV, load_config
from tests.test_runner import FAKE_OMP, STREAM


@pytest.fixture(autouse=True)
def no_ambient_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)


@pytest.fixture()
def fake_omp_env(tmp_path, monkeypatch):
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


def test_init_scaffolds_bank(tmp_path, capsys):
    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    cfg = load_config(bank / "ratchet.toml")
    assert cfg.bank_pack == bank / "tasks"
    assert (bank / "runs").is_dir() and (bank / ".gitignore").read_text() == "/runs/\n"
    split = json.loads((bank / "era" / "split.json").read_text())
    assert split["split_version"] == 0
    assert split["held_in"] == split["held_out"] == split["sentinel"] == []
    # the kit's standing overlays migrated in and are wired into the config
    names = {p.name for p in cfg.standing_overlays}
    assert names == {"eval-isolation.yml", "ctxslim-v1.yml"}
    assert all(p.is_file() for p in cfg.standing_overlays)
    # bootstrap autodetected to the kit's materialized pack
    assert (cfg.bootstrap_pack / "pack.json").is_file()

    assert main(["init", str(bank)]) == 2  # refuses to clobber


def test_missing_config_fails_closed_with_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["probe", "rules"]) == 2
    assert "ratchet init" in capsys.readouterr().err


def test_sweep_and_set_active(tmp_path, repo, fake_omp_env, monkeypatch, capsys):
    import shutil
    bank = tmp_path / "bank"
    pack = tmp_path / "minipack"
    pack.mkdir()
    shutil.copytree(repo / "tasks" / "01-py-pagination", pack / "01-py-pagination",
                    ignore=shutil.ignore_patterns("__pycache__"))
    assert main(["init", str(bank)]) == 0
    cfgp = str(bank / "ratchet.toml")

    assert main(["baseline", "sweep", "b1", "--config", cfgp, "--pack", str(pack),
                 "--tasks", "01-py-pagination", "--k", "2"]) == 0
    rows = [json.loads(l) for l in
            (bank / "runs" / "b1" / "results.jsonl").read_text().splitlines()]
    assert [r["rollout"] for r in rows] == [1, 2]
    assert all(r["label"] == "b1" and r["model"] == "vllm/homelab-default"
               for r in rows)
    assert all(r["tokens_in"] == 350 for r in rows)

    # sweep is resumable: a second call appends rather than stranding
    assert main(["baseline", "sweep", "b1", "--config", cfgp, "--pack", str(pack),
                 "--tasks", "01-py-pagination", "--k", "1"]) == 0
    assert len((bank / "runs" / "b1" / "results.jsonl").read_text().splitlines()) == 3

    # sweep cost record (#12 decision 7): totals plus the order actually used
    cost = json.loads((bank / "runs" / "b1" / "sweep_cost.json").read_text())
    assert cost["rollouts_run"] == 1 and cost["rollouts_planned"] == 1
    assert cost["tokens_in"] == 350 and cost["aborted"] is False
    assert cost["task_order"] == ["01-py-pagination"]
    assert cost["concurrency"] == 1
    assert cost["sum_rollout_duration_s"] >= 0 and cost["elapsed_wall_s"] >= 0

    assert main(["baseline", "set-active", "b1", "--config", cfgp]) == 0
    reg = json.loads((bank / "era" / "ACTIVE_BASELINE").read_text())
    assert reg["label"] == "b1" and reg["gate_version"] == 4
    assert reg["split_version"] == 0
    assert reg["concurrency"] == 1  # #12 decision 6: recorded mechanically
    assert reg["model"] == "vllm/homelab-default"
    assert set(reg["config_sha256"]) == {"overlays/eval-isolation.yml",
                                         "overlays/ctxslim-v1.yml"}


def test_set_active_missing_results_exit_2(tmp_path, capsys):
    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    assert main(["baseline", "set-active", "nope",
                 "--config", str(bank / "ratchet.toml")]) == 2
    assert "no results" in capsys.readouterr().err


def test_probe_rules_channel(tmp_path, fake_omp_env, capsys):
    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    # the fake omp echoes RULES.md, so the injected token round-trips = LIVE
    rules = tmp_path / "home" / ".omp" / "agent" / "RULES.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("# Rules\n")
    assert main(["probe", "rules", "--config", str(bank / "ratchet.toml")]) == 0
    assert "LIVE" in capsys.readouterr().out
    assert rules.read_text() == "# Rules\n"  # trap-restored after the probe
    probes = list((bank / "runs" / "probes").glob("*-rules.json"))
    assert len(probes) == 1
    rec = json.loads(probes[0].read_text())
    assert rec["observed"] is True and rec["channel"] == "rules"


def test_probe_dead_channel_exit_1(tmp_path, fake_omp_env, capsys, monkeypatch):
    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    # dead channel: nothing the model emits ever contains the token
    empty = tmp_path / "empty-stream.jsonl"
    empty.write_text("")
    monkeypatch.setenv("FAKE_OMP_STREAM", str(empty))
    monkeypatch.setenv("FAKE_OMP_MUTE_ARGS", "1")
    assert main(["probe", "append-system-prompt",
                 "--config", str(bank / "ratchet.toml")]) == 1
    assert "DEAD" in capsys.readouterr().out
