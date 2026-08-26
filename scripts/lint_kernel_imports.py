#!/usr/bin/env python3
"""Kernel purity lint (issue #2, point 2, enforced from day one).

ratchet.kernel may never import ratchet.runner or ratchet.miner, at any
import depth or inside any function. AST-based so it catches lazy imports
too. Exit 0 clean, 1 on violation.
"""

import ast
import sys
from pathlib import Path

FORBIDDEN = ("ratchet.runner", "ratchet.miner")
KERNEL = Path(__file__).resolve().parent.parent / "ratchet" / "kernel"


def violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
            if node.level:
                out.append(f"{path}:{node.lineno}: relative import in kernel "
                           "(use absolute ratchet.kernel imports)")
        for name in names:
            if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                out.append(f"{path}:{node.lineno}: kernel imports {name}")
    return out


def main() -> int:
    errs = []
    for py in sorted(KERNEL.rglob("*.py")):
        errs += violations(py)
    for e in errs:
        print(e, file=sys.stderr)
    if not errs:
        print(f"kernel import lint: clean ({len(list(KERNEL.rglob('*.py')))} files)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
