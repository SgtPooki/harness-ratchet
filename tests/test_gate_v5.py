"""Gate v5 replay against fixtures hand-authored from the spec.

tests/fixtures/gate_v5/cases.json was written by reading SPEC.md and doing the
arithmetic by hand, before the v5 implementation existed, so the code under
test is not its own oracle. Each case also carries the verdict v4 would give,
which is what makes the behaviour change visible rather than asserted.
"""

import json

import pytest

from ratchet.kernel.gate import decide

FIXTURES = "gate_v5"


def _cases(request):
    p = request.path.parent / "fixtures" / FIXTURES / "cases.json"
    return json.loads(p.read_text())


def _rows(passes: int, k: int, duration: int) -> list[dict]:
    """k rollouts of which `passes` pass, with soft axes held flat."""
    return [{"pass": i < passes, "duration_s": duration,
             "tokens_out": 1000, "tokens_in": 10000} for i in range(k)]


def _side(spec: dict, k: int, duration: int) -> dict[str, list[dict]]:
    return {t: _rows(n, k, duration) for t, n in spec.items()}


def _run(case, doc, gate_version):
    k = doc["defaults"]["k"]
    base = _side(case["baseline"], k, 100)
    cand_duration = int(100 * case.get("duration_scale", 1.0))
    cand = _side(case["candidate"], k, cand_duration)
    manifest, _ = decide(doc["split"], base, cand,
                         baseline_label="b", candidate_label="c",
                         min_k=2, effect=doc["defaults"]["effect"],
                         gate_version=gate_version,
                         material_task_delta=doc["defaults"]["material_task_delta"])
    return manifest


def _ids(doc):
    return [c["name"] for c in doc["cases"]]


@pytest.fixture
def doc(request):
    return _cases(request)


def test_every_case_matches_the_hand_authored_v5_verdict(doc):
    for case in doc["cases"]:
        m = _run(case, doc, gate_version=5)
        assert m["decision"] == case["expect_v5"], (
            f"{case['name']}: expected {case['expect_v5']} under v5, got "
            f"{m['decision']} ({m['reasons']}). {case['why']}")
        want = case.get("expect_reason_contains")
        if want:
            assert any(want in r for r in m["reasons"]), (
                f"{case['name']}: no reason containing {want!r} in {m['reasons']}")


def test_every_case_still_matches_v4_when_replayed_as_v4(doc):
    # v4 math must remain available and unchanged for historical replay.
    for case in doc["cases"]:
        m = _run(case, doc, gate_version=4)
        assert m["decision"] == case["expect_v4"], (
            f"{case['name']}: expected {case['expect_v4']} under v4 replay, "
            f"got {m['decision']} ({m['reasons']})")


def test_the_null_case_is_the_reason_v5_exists(doc):
    """An identical harness must not promote against itself."""
    case = next(c for c in doc["cases"] if c["name"] == "null_identical_harness")
    assert _run(case, doc, gate_version=4)["decision"] == "PROMOTE"
    assert _run(case, doc, gate_version=5)["decision"] == "REJECT"


def test_manifest_records_the_version_it_decided_under(doc):
    case = doc["cases"][0]
    assert _run(case, doc, gate_version=4)["gate_version"] == 4
    assert _run(case, doc, gate_version=5)["gate_version"] == 5


def test_materiality_evidence_is_recorded_when_the_pass_axis_moves(doc):
    case = next(c for c in doc["cases"] if c["name"] == "real_fix_half_the_rollouts")
    ev = _run(case, doc, gate_version=5)["evidence"]["pass_rate"]
    assert ev["best_task_delta"] == 0.5
    assert ev["material_task_delta"] == 0.5
