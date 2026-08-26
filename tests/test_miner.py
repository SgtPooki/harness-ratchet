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

SUPPORT_MODULE = '''\
UNIT = 2

def scale(x):
    return x * UNIT
'''

SCALED = '''\
from units import scale

def clamp_scaled(value, lo, hi):
    """Scale value by the unit factor, then clamp into [lo, hi]."""
    v = scale(value)
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v
'''

SCALED_TESTS = '''\
from scaled import clamp_scaled

def test_below():
    assert clamp_scaled(-5, 0, 10) == 0

def test_above():
    assert clamp_scaled(15, 0, 10) == 10

def test_inside():
    assert clamp_scaled(3, 0, 10) == 6
'''


@pytest.fixture()
def entangled_source(tmp_path):
    src = tmp_path / "srcrepo2"
    src.mkdir()
    (src / "scaled.py").write_text(SCALED)
    (src / "units.py").write_text(SUPPORT_MODULE)
    (src / "test_scaled.py").write_text(SCALED_TESTS)
    return src


def entangled_spec(src, **over):
    kw = dict(name="91-scaled", module=src / "scaled.py",
              tests=src / "test_scaled.py", function="clamp_scaled",
              prompt="Implement clamp_scaled per its docstring.",
              deps=["pytest"], support=[src / "units.py"])
    kw.update(over)
    return MintSpec(**kw)


def test_mint_support_module_admitted(entangled_source, tmp_path):
    result = mint(entangled_spec(entangled_source), tmp_path / "bank-tasks")
    assert result.admitted, result.failure_reason
    tdir = tmp_path / "bank-tasks" / "91-scaled"
    # support module lands verbatim in the workspace, the base every overlay sits on
    assert (tdir / "workspace" / "units.py").read_text() == SUPPORT_MODULE
    # solution and sabotage stay pure overlays of the target module
    assert not (tdir / "solution" / "units.py").exists()
    assert not (tdir / "sabotage" / "units.py").exists()
    # the support module is never excised or mutated
    assert "NotImplementedError" not in (tdir / "workspace" / "units.py").read_text()


def test_mint_without_support_is_baseline_broken(entangled_source, tmp_path):
    # sanity: the same target WITHOUT its support module cannot even run its
    # solution (import error), proving support is load-bearing, not cosmetic
    result = mint(entangled_spec(entangled_source, support=[]),
                  tmp_path / "bank-tasks")
    assert not result.admitted


def test_preflight_with_support(entangled_source):
    assert preflight(entangled_spec(entangled_source)) is None


def test_missing_support_module_is_mint_error(entangled_source, tmp_path):
    from ratchet.miner.excision import MintError
    spec = entangled_spec(entangled_source,
                          support=[entangled_source / "absent.py"])
    with pytest.raises(MintError):
        mint(spec, tmp_path / "bank-tasks")


def test_spec_load_support_field(tmp_path, entangled_source):
    doc = {"name": "91-scaled", "module": str(entangled_source / "scaled.py"),
           "tests": str(entangled_source / "test_scaled.py"),
           "function": "clamp_scaled", "prompt": "p", "deps": ["pytest"],
           "support": [str(entangled_source / "units.py")]}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(doc))
    spec = MintSpec.load(p)
    assert spec.support == [entangled_source / "units.py"]


PKG_UTIL = '''\
def half(x):
    return x // 2
'''

PKG_CORE = '''\
from mypkg.util import half

def bounded_half(value, hi):
    """Half the value, capped at hi."""
    v = half(value)
    if v > hi:
        return hi
    return v
'''

PKG_TEST = '''\
from mypkg.core import bounded_half
from tests.helpers import CASES

def test_cases():
    for value, hi, want in CASES:
        assert bounded_half(value, hi) == want
'''

PKG_HELPERS = '''\
CASES = [(10, 100, 5), (10, 3, 3), (0, 9, 0)]
'''


@pytest.fixture()
def package_source(tmp_path):
    src = tmp_path / "pkgrepo"
    (src / "mypkg").mkdir(parents=True)
    (src / "mypkg" / "__init__.py").write_text("")
    (src / "mypkg" / "util.py").write_text(PKG_UTIL)
    (src / "mypkg" / "core.py").write_text(PKG_CORE)
    (src / "tests").mkdir()
    (src / "tests" / "__init__.py").write_text("")
    (src / "tests" / "helpers.py").write_text(PKG_HELPERS)
    (src / "tests" / "test_core.py").write_text(PKG_TEST)
    (src / "mypkg" / "__pycache__").mkdir()
    (src / "mypkg" / "__pycache__" / "junk.pyc").write_text("x")
    return src


def package_spec(src, **over):
    kw = dict(name="92-bounded-half", module=src / "mypkg" / "core.py",
              tests=src / "tests", test_file="test_core.py",
              function="bounded_half",
              prompt="Implement bounded_half per its docstring.",
              deps=["pytest"], package_root=src / "mypkg")
    kw.update(over)
    return MintSpec(**kw)


def test_mint_package_root_admitted(package_source, tmp_path):
    result = mint(package_spec(package_source), tmp_path / "bank-tasks")
    assert result.admitted, result.failure_reason
    tdir = tmp_path / "bank-tasks" / "92-bounded-half"
    ws = tdir / "workspace" / "mypkg"
    # the whole package tree rides along, junk excluded, target excised
    assert (ws / "util.py").read_text() == PKG_UTIL
    assert (ws / "__init__.py").is_file()
    assert not (ws / "__pycache__").exists()
    assert "NotImplementedError" in (ws / "core.py").read_text()
    # solution and sabotage stay single-file overlays at the package rel
    assert (tdir / "solution" / "mypkg" / "core.py").read_text() == PKG_CORE
    assert not (tdir / "solution" / "mypkg" / "util.py").exists()
    # the tests tree (helpers and all) is the verifier
    assert (tdir / "verify" / "tests" / "helpers.py").is_file()


def test_preflight_package_root(package_source):
    assert preflight(package_spec(package_source)) is None


def test_tests_dir_requires_test_file(package_source, tmp_path):
    from ratchet.miner.excision import MintError
    with pytest.raises(MintError, match="test_file"):
        mint(package_spec(package_source, test_file=""), tmp_path / "t")


def test_module_outside_package_root_is_mint_error(package_source, tmp_path):
    from ratchet.miner.excision import MintError
    spec = package_spec(package_source,
                        module=package_source / "tests" / "helpers.py",
                        function="anything")
    with pytest.raises(MintError, match="not under"):
        mint(spec, tmp_path / "t")
