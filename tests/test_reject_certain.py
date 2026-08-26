"""The #12 early-abort certainty check: an abort may only fire when every
completion of the remaining rollouts still REJECTs under unchanged v4 math."""

import itertools

from ratchet.kernel.gate import decide, reject_certain


def rows(task, results):
    return [{"task": task, "pass": bool(p), "duration_s": 10,
             "tokens_out": 5, "tokens_in": 5, "model": "m"} for p in results]


SPLIT = {"split_version": 99, "held_in": ["A", "B"], "held_out": ["C"],
         "sentinel": ["S"]}


def test_no_abort_on_clean_partial():
    base = {t: rows(t, [1, 1]) for t in ("A", "B", "C")}
    cand = {"A": rows("A", [1])}
    assert reject_certain(SPLIT, base, cand, planned_k=2) is None


def test_first_failure_against_perfect_baseline_is_certain():
    base = {t: rows(t, [1, 1]) for t in ("A", "B", "C")}
    cand = {"A": rows("A", [0])}
    reason = reject_certain(SPLIT, base, cand, planned_k=2)
    assert reason is not None and "held_in pass certainty: A" in reason


def test_held_out_floor_certainty():
    base = {t: rows(t, [1, 1]) for t in ("A", "B", "C")}
    cand = {"A": rows("A", [1, 1]), "B": rows("B", [1, 1]), "C": rows("C", [0])}
    reason = reject_certain(SPLIT, base, cand, planned_k=2)
    assert reason is not None and "held_out pass certainty: C" in reason


def test_equality_is_non_regression_never_aborts():
    # baseline 1/2; candidate fails one of planned 2 -> best 1/2 ties, no abort
    base = {"A": rows("A", [1, 0]), "B": rows("B", [1, 1]), "C": rows("C", [1, 1])}
    cand = {"A": rows("A", [0])}
    assert reject_certain(SPLIT, base, cand, planned_k=2) is None


def test_planned_k_tracks_escalation():
    # baseline 3/4; one failure in a k=2 screen is certain (best 1/2 < 3/4)
    # but the same single failure at planned_k=4 is not (best 3/4 ties)
    base = {"A": rows("A", [1, 1, 1, 0]), "B": rows("B", [1] * 4),
            "C": rows("C", [1] * 4)}
    cand = {"A": rows("A", [0])}
    assert reject_certain(SPLIT, base, cand, planned_k=2) is not None
    assert reject_certain(SPLIT, base, cand, planned_k=4) is None


def test_sentinels_never_considered():
    base = {t: rows(t, [1, 1]) for t in ("A", "B", "C", "S")}
    cand = {"A": rows("A", [1, 1]), "B": rows("B", [1, 1]),
            "C": rows("C", [1, 1]), "S": rows("S", [0, 0])}
    assert reject_certain(SPLIT, base, cand, planned_k=2) is None


def test_certainty_implies_reject_exhaustively():
    """Property check (the resolution's verified-empirically claim, kept as
    a regression test at reduced size): whenever reject_certain fires, the
    best-case completion (all remaining rollouts pass, all other tasks
    perfect) still REJECTs. Pass-rate regression is monotone in failures,
    so best-case coverage suffices."""
    split = {"split_version": 99, "held_in": ["A"], "held_out": ["C"],
             "sentinel": []}
    triggered = 0
    for k in (2, 4):
        for base_pat in itertools.product([0, 1], repeat=2 * k):
            base = {"A": rows("A", base_pat[:k]), "C": rows("C", base_pat[k:])}
            for done in range(k + 1):
                for pat in itertools.product([0, 1], repeat=done):
                    cand_a = rows("A", list(pat))
                    if reject_certain(split, base, {"A": cand_a}, k) is None:
                        continue
                    triggered += 1
                    completion = list(pat) + [1] * (k - done)
                    cand = {"A": rows("A", completion), "C": rows("C", [1] * k)}
                    m, code = decide(split, base, cand, baseline_label="b",
                                     candidate_label="c", min_k=2)
                    assert m["decision"] == "REJECT", (k, base_pat, pat)
    assert triggered > 0
