"""Kernel purity (issue #2, point 2): the lint is green today and actually
catches a violation."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINT = REPO / "scripts" / "lint_kernel_imports.py"


def test_kernel_is_pure():
    r = subprocess.run([sys.executable, str(LINT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_lint_catches_violation(tmp_path, monkeypatch):
    sys.path.insert(0, str(LINT.parent))
    try:
        import lint_kernel_imports as lint
    finally:
        sys.path.pop(0)
    bad = tmp_path / "impure.py"
    bad.write_text("def f():\n    from ratchet.runner import omp\n")
    assert any("imports ratchet.runner" in v for v in lint.violations(bad))
    ok = tmp_path / "pure.py"
    ok.write_text("import json\nfrom ratchet.kernel.digests import pack_digest\n")
    assert lint.violations(ok) == []
