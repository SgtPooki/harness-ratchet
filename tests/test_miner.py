"""Miner: excision, mutant hunt inside the excised function, the seven-value
failure enum, preflight, and the mint verb's bank bookkeeping."""

import json
from pathlib import Path

import pytest

from ratchet.cli import main
from ratchet.config import CONFIG_ENV
from ratchet.kernel.pack import validate_pack
from ratchet.miner.excision import (
    FAILURE_ENUM,
    MintSpec,
    excise,
    mint,
    mutants,
    preflight,
)

MODULE = '''\
def clamp(value, lo, hi):
    """Clamp value into [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def helper_untested(x):
    return x == 0
'''

TESTS = '''\
from clamp import clamp

def test_below():
    assert clamp(-5, 0, 10) == 0

def test_above():
    assert clamp(15, 0, 10) == 10

def test_inside():
    assert clamp(5, 0, 10) == 5
'''


@pytest.fixture(autouse=True)
def no_ambient_config(monkeypatch):
    monkeypatch.delenv(CONFIG_ENV, raising=False)


@pytest.fixture()
def source(tmp_path):
    src = tmp_path / "srcrepo"
    src.mkdir()
    (src / "clamp.py").write_text(MODULE)
    (src / "test_clamp.py").write_text(TESTS)
    return src


def spec_for(source, tmp_path, **over):
    kw = dict(name="90-clamp", module=source / "clamp.py",
              tests=source / "test_clamp.py", function="clamp",
              prompt="Implement clamp per its docstring.", deps=["pytest"])
    kw.update(over)
    return MintSpec(**kw)


def test_excise_keeps_docstring(source, tmp_path):
    out = excise(MODULE, "clamp")
    assert '"""Clamp value into [lo, hi]."""' in out
    assert "NotImplementedError" in out
    assert "value < lo" not in out
    assert "helper_untested" in out  # rest of the module untouched


def test_mutants_only_inside_target():
    ms = list(mutants(MODULE, "clamp"))
    assert len(ms) == 2  # the two comparisons in clamp; helper's == excluded
    assert all("helper_untested(x):\n    return x == 0" in m for m in ms)


def test_mint_admitted(source, tmp_path):
    result = mint(spec_for(source, tmp_path), tmp_path / "bank-tasks")
    assert result.admitted, result.failure_reason
    assert result.oracle_triple == {"unmodified_fails": True,
                                    "solution_passes": True,
                                    "sabotage_fails": True}
    assert result.mutants == {"killed": 2, "total": 2}
    assert result.stability == [True, True, True]
    tdir = tmp_path / "bank-tasks" / "90-clamp"
    assert (tdir / "workspace" / "clamp.py").is_file()
    assert (tdir / "sabotage" / "clamp.py").is_file()
    assert "NotImplementedError" in (tdir / "workspace" / "clamp.py").read_text()


def test_mint_vacuous_task(source, tmp_path):
    (source / "test_clamp.py").write_text("def test_nothing():\n    assert True\n")
    result = mint(spec_for(source, tmp_path), tmp_path / "out")
    assert result.outcome == "rejected"
    assert result.failure_reason == "vacuous-task"
    assert not (tmp_path / "out" / "90-clamp").exists()


def test_mint_solution_fails(source, tmp_path):
    (source / "test_clamp.py").write_text(
        TESTS + "\ndef test_wrong():\n    assert clamp(5, 0, 10) == 99\n")
    result = mint(spec_for(source, tmp_path), tmp_path / "out")
    assert result.failure_reason == "solution-fails"


def test_mint_no_comparison_is_excision_error(source, tmp_path):
    (source / "noop.py").write_text(
        'def add(a, b):\n    """Add."""\n    return a + b\n')
    (source / "test_noop.py").write_text(
        "from noop import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    result = mint(spec_for(source, tmp_path, name="91-noop",
                           module=source / "noop.py",
                           tests=source / "test_noop.py", function="add"),
                  tmp_path / "out")
    assert result.failure_reason == "excision-error"


def test_mint_weak_oracle(source, tmp_path):
    # tests exercise clamp only inside the range: no flip is ever killed
    (source / "test_clamp.py").write_text(
        "from clamp import clamp\n\ndef test_calls():\n    clamp(5, 0, 10)\n")
    result = mint(spec_for(source, tmp_path), tmp_path / "out")
    assert result.failure_reason in ("weak-oracle", "vacuous-task")
    assert result.failure_reason in FAILURE_ENUM


def test_preflight_baseline_failure(source, tmp_path):
    (source / "test_clamp.py").write_text(
        "from clamp import clamp\n\ndef test_flaky():\n    assert clamp(1, 0, 10) == 2\n")
    assert preflight(spec_for(source, tmp_path)) == "baseline-failure"
    (source / "test_clamp.py").write_text(TESTS)
    assert preflight(spec_for(source, tmp_path)) is None


def test_mint_verb_deposits_and_logs(source, tmp_path, capsys):
    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({
        "name": "90-clamp", "module": str(source / "clamp.py"),
        "tests": str(source / "test_clamp.py"), "function": "clamp",
        "prompt": "Implement clamp per its docstring.", "deps": ["pytest"]}))
    cfgp = str(bank / "ratchet.toml")

    # dry-run leaves the bank untouched but logs the attempt
    assert main(["mint", str(spec_path), "--config", cfgp]) == 0
    assert not (bank / "tasks" / "90-clamp").exists()

    assert main(["mint", str(spec_path), "--config", cfgp, "--admit",
                 "--preflight"]) == 0
    out = capsys.readouterr().out
    assert "ADMITTED" in out
    assert validate_pack(bank / "tasks") == []
    manifest = json.loads((bank / "tasks" / "pack.json").read_text())
    assert manifest["tasks"] == ["90-clamp"] and manifest["vintage"]["number"] == 1
    admission = json.loads((bank / "tasks" / "90-clamp" / "admission.json").read_text())
    assert admission["mutants"] == {"killed": 2, "total": 2}
    assert admission["sabotage"] == "present"

    rows = [json.loads(l) for l in (bank / "mint-log.jsonl").read_text().splitlines()]
    assert len(rows) == 2  # dry-run + admit
    assert rows[-1]["outcome"] == "admitted"
    assert rows[-1]["stability"] == [True, True, True]
    assert rows[-1]["target_locator"]["function"] == "clamp"

    # a second admit of the same name fails as a usage error, log intact
    assert main(["mint", str(spec_path), "--config", cfgp, "--admit"]) == 2


def test_mint_verb_rejected_logs_reason(source, tmp_path, capsys):
    bank = tmp_path / "bank"
    assert main(["init", str(bank)]) == 0
    (source / "test_clamp.py").write_text("def test_nothing():\n    assert True\n")
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps({
        "name": "90-clamp", "module": str(source / "clamp.py"),
        "tests": str(source / "test_clamp.py"), "function": "clamp",
        "prompt": "p", "deps": ["pytest"]}))
    assert main(["mint", str(spec_path), "--config", str(bank / "ratchet.toml"),
                 "--admit"]) == 1
    rows = [json.loads(l) for l in (bank / "mint-log.jsonl").read_text().splitlines()]
    assert rows[-1]["failure_reason"] == "vacuous-task"
    assert not (bank / "tasks" / "90-clamp").exists()
    assert not (bank / "tasks" / "pack.json").exists()  # nothing deposited