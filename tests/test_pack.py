"""Pack materialization and validation (issues #3 and #2 point 7): the
bootstrap tasks/ directory becomes a pack with ZERO content changes to the
task surfaces; wrapper metadata is additive; schema and set-equality and
digest checks are mechanical."""

import json
import shutil

import pytest

from ratchet.kernel.digests import pack_digest
from ratchet.kernel.oracle import AdmissionResult
from ratchet.kernel.pack import (
    PackError,
    infer_requires,
    load_pack,
    materialize_bootstrap,
    validate_pack,
)
from ratchet.kernel.schemas import validation_errors

SURFACE_FILES = ("prompt.md", "workspace", "verify", "solution", "sabotage")


def fake_admissions(root):
    out = {}
    for p in sorted(d for d in root.iterdir() if d.is_dir()):
        has_sab = (p / "sabotage").is_dir()
        out[p.name] = AdmissionResult(
            task_id=p.name, unmodified_fails=True, solution_passes=True,
            sabotage="present" if has_sab else "absent-grandfathered",
            sabotage_fails=True if has_sab else None, ok=True)
    return out


@pytest.fixture()
def tasks_copy(tmp_path, repo):
    dst = tmp_path / "tasks"
    shutil.copytree(repo / "tasks", dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc",
                                                  "pack.json", "task.json",
                                                  "admission.json"))
    return dst


def surface_snapshot(root):
    snap = {}
    for task in sorted(d for d in root.iterdir() if d.is_dir()):
        for name in SURFACE_FILES:
            p = task / name
            if not p.exists():
                continue
            files = [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file())
            for f in files:
                snap[str(f.relative_to(root))] = f.read_bytes()
    return snap


def test_materialize_bootstrap_zero_content_change(tasks_copy):
    before = surface_snapshot(tasks_copy)
    manifest = materialize_bootstrap(
        tasks_copy, name="bootstrap", vintage_number=1, vintage_date="2026-08-26",
        minted_date="2026-08-26", admissions=fake_admissions(tasks_copy),
        miner_name="ratchet-audit", miner_version="0.1.0")
    assert surface_snapshot(tasks_copy) == before

    added = {p.name for p in tasks_copy.rglob("*") if p.is_file()} - \
            {p.rsplit("/", 1)[-1] for p in before}
    assert added <= {"pack.json", "task.json", "admission.json"}

    assert manifest["tasks"] == sorted(fake_admissions(tasks_copy))
    assert manifest["digest"] == pack_digest(tasks_copy)
    assert validate_pack(tasks_copy) == []
    pack = load_pack(tasks_copy)
    assert len(pack.task_ids) == 9


def test_materialize_refuses_overwrite_without_force(tasks_copy):
    adm = fake_admissions(tasks_copy)
    kwargs = dict(name="bootstrap", vintage_number=1, vintage_date="2026-08-26",
                  minted_date="2026-08-26", admissions=adm,
                  miner_name="ratchet-audit", miner_version="0.1.0")
    materialize_bootstrap(tasks_copy, **kwargs)
    with pytest.raises(PackError, match="already exists"):
        materialize_bootstrap(tasks_copy, **kwargs)
    materialize_bootstrap(tasks_copy, force=True, **kwargs)


def test_materialize_refuses_failed_admission(tasks_copy):
    adm = fake_admissions(tasks_copy)
    adm["01-py-pagination"].ok = False
    with pytest.raises(PackError, match="failed admissions"):
        materialize_bootstrap(
            tasks_copy, name="bootstrap", vintage_number=1,
            vintage_date="2026-08-26", minted_date="2026-08-26", admissions=adm,
            miner_name="ratchet-audit", miner_version="0.1.0")


@pytest.fixture()
def valid_pack(tasks_copy):
    materialize_bootstrap(
        tasks_copy, name="bootstrap", vintage_number=1, vintage_date="2026-08-26",
        minted_date="2026-08-26", admissions=fake_admissions(tasks_copy),
        miner_name="ratchet-audit", miner_version="0.1.0")
    return tasks_copy


def test_validate_catches_set_inequality(valid_pack):
    (valid_pack / "99-stray").mkdir()
    errs = validate_pack(valid_pack)
    assert any("not listed in pack.json" in e for e in errs)

    shutil.rmtree(valid_pack / "99-stray")
    shutil.rmtree(valid_pack / "01-py-pagination")
    errs = validate_pack(valid_pack)
    assert any("no directory" in e for e in errs)


def test_validate_catches_digest_mismatch(valid_pack):
    (valid_pack / "01-py-pagination" / "prompt.md").write_text("tampered\n")
    errs = validate_pack(valid_pack)
    assert any("digest mismatch" in e for e in errs)


def test_validate_catches_self_declared_grandfather(valid_pack):
    """A pack cannot self-declare absent-grandfathered for a task off the
    kernel allowlist (issue #3, point 4)."""
    tdir = valid_pack / "01-py-pagination"
    shutil.rmtree(tdir / "sabotage")
    rec = json.loads((tdir / "admission.json").read_text())
    rec["sabotage"] = "absent-grandfathered"
    (tdir / "admission.json").write_text(json.dumps(rec))
    errs = validate_pack(valid_pack)
    assert any("not on the kernel grandfather allowlist" in e for e in errs)


def test_schema_rejects_unknown_requires():
    doc = {"id": "x", "requires": ["cargo"],
           "surfaces": {s: {"encryption": "plaintext"}
                        for s in ("agent", "scoring", "admission")}}
    assert any("cargo" in e for e in validation_errors("task", doc))


def test_schema_rejects_bad_vintage():
    doc = {"format_version": 1, "name": "p", "vintage": {"number": 0, "date": "2026-08-26"},
           "digest_algorithm": "hr-pd-1", "digest": "a" * 64, "tasks": []}
    assert validation_errors("pack", doc)


def test_infer_requires(repo):
    assert infer_requires(repo / "tasks" / "01-py-pagination") == ["python3"]
    assert infer_requires(repo / "tasks" / "03-js-slugify") == ["node"]
    assert infer_requires(repo / "tasks" / "04-sh-backup") == ["python3", "bash"]
    assert infer_requires(repo / "tasks" / "09-proxy-concurrency-cap") == ["python3", "uv"]
