"""Gate-math golden replay (issue #2, points 6-7).

The expected outputs were frozen ONCE from the pre-port bin/gate.py v4
math (tests/fixtures/gate/freeze_fixtures.py); the ported kernel gate must
reproduce every one of the 156 ordered pairs exactly. Never regenerate the
fixtures from the ported code.
"""

import json

import pytest

from ratchet.kernel.gate import decide, load_results

PINNED_COMMIT = "0" * 40


def _expected(gate_fixtures):
    return json.loads((gate_fixtures / "expected.json").read_text())


def test_fixture_count(gate_fixtures):
    exp = _expected(gate_fixtures)
    labels = {p.name for p in (gate_fixtures / "runs").iterdir() if p.is_dir()}
    assert len(exp) == len(labels) * (len(labels) - 1) == 156


def pytest_generate_tests(metafunc):
    if "pair" in metafunc.fixturenames:
        fixtures = metafunc.config.rootpath / "tests" / "fixtures" / "gate"
        pairs = sorted(json.loads((fixtures / "expected.json").read_text()))
        metafunc.parametrize("pair", pairs)


@pytest.fixture(scope="module")
def split(gate_fixtures):
    return json.loads((gate_fixtures / "split.json").read_text())


def test_golden_pair(pair, split, gate_fixtures):
    expected = _expected(gate_fixtures)[pair]
    base_label, cand_label = pair.split("__")
    base = load_results(gate_fixtures / "runs" / base_label / "results.jsonl")
    cand = load_results(gate_fixtures / "runs" / cand_label / "results.jsonl")
    # Replayed as v4 on purpose: these fixtures were frozen from the v4 math,
    # so they are the regression test for v4 remaining available and unchanged,
    # not for whatever the current default version does.
    manifest, code = decide(
        split, base, cand, baseline_label=base_label, candidate_label=cand_label,
        min_k=2, effect=0.15, rollback_target=PINNED_COMMIT, gate_version=4,
    )
    # round-trip through JSON so float/int representation matches the fixture
    assert json.loads(json.dumps(manifest)) == expected["manifest"]
    assert code == expected["exit"]
