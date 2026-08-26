"""Operator config resolution and validation (issue #2, point 3)."""

import pytest

from ratchet.config import CONFIG_ENV, ConfigError, find_config, load_config

MINIMAL = """\
[paths]
runs_dir = "runs"
era_dir = "era"
[packs]
bootstrap = "packs/bootstrap"
bank = "tasks"
[runner]
harness = "omp"
model = "vllm/homelab-default"
timeout_s = 900
k = 2
"""


def write_cfg(root, body=MINIMAL, name="ratchet.toml"):
    root.mkdir(parents=True, exist_ok=True)
    p = root / name
    p.write_text(body)
    return p


def test_resolution_order(tmp_path, monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    walk = write_cfg(tmp_path / "bank")
    nested = tmp_path / "bank" / "deep" / "er"
    nested.mkdir(parents=True)
    assert find_config(cwd=nested) == walk           # cwd-walk finds the bank root

    env_cfg = write_cfg(tmp_path / "elsewhere")
    monkeypatch.setenv(CONFIG_ENV, str(env_cfg))
    assert find_config(cwd=nested) == env_cfg        # env beats the walk

    explicit = write_cfg(tmp_path / "explicit")
    assert find_config(explicit, cwd=nested) == explicit  # flag beats env


def test_fail_closed_points_at_init(tmp_path, monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    with pytest.raises(ConfigError, match="ratchet init"):
        find_config(cwd=tmp_path)


def test_paths_resolve_relative_to_toml(tmp_path, monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    p = write_cfg(tmp_path / "bank")
    cfg = load_config(p)
    assert cfg.runs_dir == tmp_path / "bank" / "runs"
    assert cfg.bank_pack == tmp_path / "bank" / "tasks"
    assert cfg.split_file == tmp_path / "bank" / "era" / "split.json"
    assert cfg.k == 2 and cfg.timeout_s == 900


def test_missing_section_and_key(tmp_path):
    p = write_cfg(tmp_path, MINIMAL.replace('[runner]\nharness = "omp"\n', "[runner]\n"))
    with pytest.raises(ConfigError, match="runner.harness"):
        load_config(p)
    p = write_cfg(tmp_path, MINIMAL.replace('era_dir = "era"\n', ""), name="broken.toml")
    with pytest.raises(ConfigError, match="paths.era_dir"):
        load_config(p)
    p = write_cfg(tmp_path, "[paths]\nruns_dir = 'runs'\n", name="nosection.toml")
    with pytest.raises(ConfigError, match=r"missing \[packs\] section"):
        load_config(p)


def test_standing_overlays_must_exist(tmp_path):
    body = MINIMAL + '[overlays.standing]\npaths = ["overlays/iso.yml"]\n'
    p = write_cfg(tmp_path / "bank", body)
    with pytest.raises(ConfigError, match="standing overlays not found"):
        load_config(p)
    ov = tmp_path / "bank" / "overlays" / "iso.yml"
    ov.parent.mkdir(parents=True)
    ov.write_text("advisor:\n  enabled: false\n")
    assert load_config(p).standing_overlays == [ov]
