"""CLI shape: eight verbs exist; deferred verbs exit 2 with a pointer."""

import pytest

from ratchet.cli import main


@pytest.mark.parametrize("verb", ["mint", "click", "export", "replicate"])
def test_deferred_verbs_exit_2(verb, capsys):
    assert main([verb]) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_unknown_verb_rejected():
    with pytest.raises(SystemExit):
        main(["promote"])


def test_audit_missing_pack_dir_exit_2(tmp_path, capsys):
    assert main(["audit", "--pack", str(tmp_path / "nope")]) == 2


def test_audit_fails_on_broken_synthetic_pack(tmp_path, repo, capsys):
    import shutil
    dst = tmp_path / "pack" / "01-py-pagination"
    shutil.copytree(repo / "tasks" / "01-py-pagination", dst,
                    ignore=shutil.ignore_patterns("__pycache__"))
    # break the reference solution: audit must fail, materialize must refuse
    (dst / "solution" / "paginate.py").write_text("def paginate(*a):\n    return []\n")
    assert main(["audit", "--pack", str(tmp_path / "pack")]) == 1
    assert "ORACLE FAIL" in capsys.readouterr().out
    assert main(["audit", "--pack", str(tmp_path / "pack"), "--materialize"]) == 1
    assert not (tmp_path / "pack" / "pack.json").exists()


def test_audit_and_materialize_roundtrip(tmp_path, repo, capsys):
    import shutil
    root = tmp_path / "pack"
    root.mkdir()
    shutil.copytree(repo / "tasks" / "01-py-pagination", root / "01-py-pagination",
                    ignore=shutil.ignore_patterns("__pycache__"))
    assert main(["audit", "--pack", str(root), "--materialize", "--name", "mini"]) == 0
    out = capsys.readouterr().out
    assert "materialized pack 'mini'" in out
    # re-audit of the materialized pack re-executes and matches the records
    assert main(["audit", "--pack", str(root)]) == 0
