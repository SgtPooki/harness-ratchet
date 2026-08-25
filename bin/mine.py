#!/usr/bin/env python3
"""Excision miner v1 — mint a task from a real repo's module + test pair.

Usage:
  bin/mine.py spec.json [--admit]

spec.json:
  {
    "name": "10-something",             // task dir name
    "module": "/abs/path/to/module.py", // file whose function gets excised
    "tests": "/abs/path/to/test_x.py",  // existing tests = the hidden oracle
    "function": "dispatch",             // function/method name to excise
    "deps": ["pytest", "pytest-asyncio", "httpx", "starlette"],
    "prompt": "one-paragraph task statement shown to the agent",
    "pytest_args": ["-o", "asyncio_mode=auto"]   // optional
  }

Pipeline (FeatureBench pattern — the generator NEVER authors the oracle):
  1. Excise the named function's body -> NotImplementedError stub, docstring
     kept (the docstring is the visible spec — write a good one first).
  2. solution/ = original module. sabotage/ = first-order AST mutant of the
     original (first comparison operator flipped); if the tests cannot kill
     the mutant, the task is REJECTED (weak oracle).
  3. verify/verify.py runs the tests hermetically via uv with the declared
     deps, PYTHONPATH=workspace.
  4. Admission audit: oracle triple (unmodified FAILS / solution PASSES /
     sabotage FAILS) + REAP stability (3 identical solution verdicts).
  --admit actually writes tasks/<name>/; without it, dry-run to a temp dir.
"""

import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FLIP = {ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In}


def excise(src, func_name):
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            body_start = node.body[0].lineno
            # keep a leading docstring if present
            if (isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                body_start = node.body[0].end_lineno + 1
            indent = " " * (node.col_offset + 4)
            stub = f'{indent}raise NotImplementedError("excised by harness-ratchet miner")\n'
            return "".join(lines[:body_start - 1]) + stub + "".join(lines[node.end_lineno:])
    raise SystemExit(f"mine: function {func_name!r} not found")


def mutate(src):
    """Flip the first comparison operator found inside any function body."""
    class Flipper(ast.NodeTransformer):
        def __init__(self):
            self.done = False

        def visit_Compare(self, node):
            if not self.done and type(node.ops[0]) in FLIP:
                node.ops[0] = FLIP[type(node.ops[0])]()
                self.done = True
            return node

    tree = ast.parse(src)
    f = Flipper()
    tree = f.visit(tree)
    if not f.done:
        raise SystemExit("mine: no comparison operator to mutate — supply sabotage/ manually")
    return ast.unparse(tree) + "\n"


def write_verify(vdir, test_name, deps, pytest_args):
    with_args = " ".join(f'"--with", "{d}",' for d in deps)
    extra = "".join(f' "{a}",' for a in pytest_args)
    (vdir / "verify.py").write_text(f'''import os, subprocess, sys
ws = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
here = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run(["uv", "run", "--quiet", "--no-project", {with_args}
     "pytest", "-q", "-p", "no:cacheprovider",{extra}
     os.path.join(here, "{test_name}")],
    env=dict(os.environ, PYTHONPATH=ws), capture_output=True, text=True, timeout=300)
if r.returncode != 0:
    print(r.stdout[-1500:]); print(r.stderr[-500:]); raise SystemExit(1)
print("PASS")
''')


def run_verify(vdir, ws):
    return subprocess.run([sys.executable, str(vdir / "verify.py"), str(ws)],
                          capture_output=True, text=True, timeout=400)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    admit = "--admit" in sys.argv
    module, tests = Path(spec["module"]), Path(spec["tests"])
    src = module.read_text()

    base = ROOT / "tasks" / spec["name"] if admit else Path(tempfile.mkdtemp(prefix="mine-"))
    if admit and base.exists():
        sys.exit(f"mine: {base} already exists")
    for d in ("workspace", "verify", "solution", "sabotage"):
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / "workspace" / module.name).write_text(excise(src, spec["function"]))
    (base / "solution" / module.name).write_text(src)
    (base / "sabotage" / module.name).write_text(mutate(src))
    shutil.copy(tests, base / "verify" / tests.name)
    (base / "prompt.md").write_text(spec["prompt"].rstrip() + "\n")
    write_verify(base / "verify", tests.name, spec["deps"], spec.get("pytest_args", []))

    # Admission audit
    verdicts = {}
    for variant, overlays in (("unmodified", []), ("solution", ["solution"]),
                              ("sabotage", ["solution", "sabotage"])):
        tmp = Path(tempfile.mkdtemp())
        shutil.copytree(base / "workspace", tmp, dirs_exist_ok=True)
        for o in overlays:
            shutil.copytree(base / o, tmp, dirs_exist_ok=True)
        verdicts[variant] = run_verify(base / "verify", tmp).returncode == 0
        shutil.rmtree(tmp)
    stable = all(
        run_verify(base / "verify",
                   (lambda t: (shutil.copytree(base / "workspace", t, dirs_exist_ok=True),
                               shutil.copytree(base / "solution", t, dirs_exist_ok=True), t)[-1])(
                       Path(tempfile.mkdtemp()))).returncode == 0
        for _ in range(3))

    ok = (not verdicts["unmodified"]) and verdicts["solution"] and (not verdicts["sabotage"]) and stable
    print(f"unmodified fails: {not verdicts['unmodified']} | solution passes: {verdicts['solution']} | "
          f"sabotage fails: {not verdicts['sabotage']} | stable x3: {stable}")
    print(f"{'ADMITTED' if ok else 'REJECTED'}: {base}")
    if not ok and admit:
        shutil.rmtree(base)
        print("(removed — fix the spec or the tests and retry)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
