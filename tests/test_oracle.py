"""Oracle-triple admission over the bootstrap pack (issue #2, point 7),
including the five absent-grandfathered tasks, plus synthetic failure legs."""

import shutil

import pytest

from ratchet.kernel.oracle import GRANDFATHERED_SABOTAGE, admit_task

BOOTSTRAP_SABOTAGE = {"01-py-pagination", "04-sh-backup", "07-py-lru-ttl",
                      "09-proxy-concurrency-cap"}


def bootstrap_task_dirs(repo):
    return sorted(p for p in (repo / "tasks").iterdir() if p.is_dir())


def test_grandfather_allowlist_is_locked():
    # Issue #3 amendment: explicit ids, hardcoded kernel-side.
    assert GRANDFATHERED_SABOTAGE == {
        "02-py-config-type", "03-js-slugify", "05-py-dedupe",
        "06-py-version-sync", "08-py-report-bleed"}


@pytest.mark.parametrize("task_id", [
    "01-py-pagination", "02-py-config-type", "03-js-slugify", "04-sh-backup",
    "05-py-dedupe", "06-py-version-sync", "07-py-lru-ttl", "08-py-report-bleed",
    "09-proxy-concurrency-cap"])
def test_bootstrap_task_admitted(repo, task_id):
    res = admit_task(repo / "tasks" / task_id)
    assert res.ok, res.reasons
    assert res.unmodified_fails and res.solution_passes
    if task_id in BOOTSTRAP_SABOTAGE:
        assert res.sabotage == "present" and res.sabotage_fails is True
    else:
        assert res.sabotage == "absent-grandfathered"
        assert res.sabotage_fails is None


def synthetic_task(root, repo, *, vacuous=False, broken_solution=False,
                   weak_sabotage=False, name="90-synthetic"):
    """Clone the tiny 01 task and break one admission leg."""
    src = repo / "tasks" / "01-py-pagination"
    dst = root / name
    shutil.copytree(src, dst)
    if vacuous:  # unmodified workspace already passes
        shutil.copytree(dst / "solution", dst / "workspace", dirs_exist_ok=True)
    if broken_solution:
        (dst / "solution" / "paginate.py").write_text("def paginate(*a):\n    return []\n")
    if weak_sabotage:  # sabotage identical to the solution: verifier can't fail it
        shutil.rmtree(dst / "sabotage")
        shutil.copytree(dst / "solution", dst / "sabotage")
    return dst


def test_vacuous_task_rejected(tmp_path, repo):
    res = admit_task(synthetic_task(tmp_path, repo, vacuous=True))
    assert not res.ok
    assert any("vacuous" in r for r in res.reasons)


def test_broken_solution_rejected(tmp_path, repo):
    res = admit_task(synthetic_task(tmp_path, repo, broken_solution=True))
    assert not res.ok
    assert any("solution does not pass" in r for r in res.reasons)


def test_weak_sabotage_rejected(tmp_path, repo):
    res = admit_task(synthetic_task(tmp_path, repo, weak_sabotage=True))
    assert not res.ok
    assert any("too weak" in r for r in res.reasons)


def test_missing_sabotage_not_grandfathered_rejected(tmp_path, repo):
    t = synthetic_task(tmp_path, repo)
    shutil.rmtree(t / "sabotage")
    res = admit_task(t)
    assert not res.ok
    assert res.sabotage == "absent"
    assert any("grandfathered" in r for r in res.reasons)


def test_missing_sabotage_grandfathered_id_admitted(tmp_path, repo):
    # The allowlist keys on the task id, never on pack payload.
    t = synthetic_task(tmp_path, repo, name="05-py-dedupe")
    shutil.rmtree(t / "sabotage")
    res = admit_task(t)
    assert res.ok
    assert res.sabotage == "absent-grandfathered"


def test_missing_verifier_rejected(tmp_path, repo):
    t = synthetic_task(tmp_path, repo)
    shutil.rmtree(t / "verify")
    res = admit_task(t)
    assert not res.ok
    assert any("no verifier" in r for r in res.reasons)
