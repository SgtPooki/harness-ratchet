"""Excision producer: mint a task from a real repo's module + test pair.

Port of bin/mine.py's minting half (issue #2, point 5: excision -> miner,
admission -> kernel). The FeatureBench pattern: the generator NEVER
authors the oracle (invariant 2) — the source repo's existing tests are
the hidden verifier.

Pipeline:
  1. Excise the named function's body -> NotImplementedError stub,
     docstring kept (the docstring is the visible spec).
  2. solution/ = original module. sabotage/ = the first comparison-flip
     mutant of the excised function the tests kill; the kill ratio over
     all its flip-mutants is reported so weak spots stay visible.
  3. verify/verify.py runs the tests hermetically via uv with declared
     deps, PYTHONPATH=workspace.
  4. Admission: the kernel oracle triple plus REAP stability (3 identical
     solution verdicts).

Outcomes use the locked seven-value failure enum (issue #8, point 4):
vacuous-task | weak-oracle | unstable | dep-failure | excision-error |
solution-fails | baseline-failure. The taxonomy grows no further.
"""

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

FAILURE_ENUM = ("vacuous-task", "weak-oracle", "unstable", "dep-failure",
                "excision-error", "solution-fails", "baseline-failure")

FLIP = {ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
        ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.In: ast.NotIn, ast.NotIn: ast.In}


class MintError(Exception):
    """Spec or source problems that are usage errors, not mint outcomes."""


@dataclass
class MintSpec:
    name: str
    module: Path
    tests: Path
    function: str
    prompt: str
    deps: list[str]
    package: str = ""
    pytest_args: list[str] = field(default_factory=list)
    # Sibling modules the target module (or its tests) imports, copied
    # byte-verbatim into the workspace beside the target module. Never
    # excised, never mutated: they are context, not the task.
    support: list[Path] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "MintSpec":
        doc = json.loads(Path(path).read_text())
        try:
            return cls(name=doc["name"], module=Path(doc["module"]),
                       tests=Path(doc["tests"]), function=doc["function"],
                       prompt=doc["prompt"], deps=list(doc["deps"]),
                       package=doc.get("package", ""),
                       pytest_args=list(doc.get("pytest_args", [])),
                       support=[Path(p) for p in doc.get("support", [])])
        except KeyError as e:
            raise MintError(f"{path}: spec missing {e}") from e


@dataclass
class MintResult:
    name: str
    outcome: str                       # admitted | rejected
    failure_reason: str | None         # from FAILURE_ENUM; None when admitted
    oracle_triple: dict
    mutants: dict                      # {"killed": int, "total": int}
    stability: list[bool]
    task_dir: Path | None              # populated when admitted
    duration_s: int = 0

    @property
    def admitted(self) -> bool:
        return self.outcome == "admitted"


def excise(src: str, func_name: str) -> str:
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
    raise MintError(f"mine: function {func_name!r} not found")


def mutants(src: str, func_name: str):
    """Yield one flipped-comparison mutant per Compare op INSIDE the excised
    function (a flip elsewhere — e.g. in a helper the tests mock — proves
    nothing about the oracle; the task-10 minting lesson)."""
    count = 0
    while True:
        class Flipper(ast.NodeTransformer):
            seen = 0
            done = False

            def visit_Compare(self, node):
                self.generic_visit(node)
                if not self.done and type(node.ops[0]) in FLIP:
                    if self.seen == count:
                        node.ops[0] = FLIP[type(node.ops[0])]()
                        self.done = True
                    self.seen += 1
                return node

        tree = ast.parse(src)
        target = next((n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and n.name == func_name), None)
        if target is None:
            raise MintError(f"mine: function {func_name!r} not found")
        f = Flipper()
        f.visit(target)
        if not f.done:
            return
        yield ast.unparse(tree) + "\n"
        count += 1


def write_verify(vdir: Path, test_name: str, deps: list[str],
                 pytest_args: list[str]) -> None:
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


def _run_verify(vdir: Path, ws: Path) -> bool:
    r = subprocess.run([sys.executable, str(vdir / "verify.py"), str(ws)],
                       capture_output=True, text=True, timeout=400)
    return r.returncode == 0


def preflight(spec: MintSpec, runs: int = 2) -> str | None:
    """Public-source preflight (issue #8, point 3): the selected tests must
    pass TWICE on the unmodified source under the miner's verify pattern
    before any excision. Returns a failure reason or None."""
    tmp = Path(tempfile.mkdtemp(prefix="mine-preflight-"))
    try:
        rel = _module_rel(spec)
        (tmp / "ws" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / "ws" / rel).write_text(spec.module.read_text())
        _write_support(tmp / "ws", spec)
        _write_package_inits(tmp / "ws", spec)
        vdir = tmp / "verify"
        vdir.mkdir()
        shutil.copy(spec.tests, vdir / spec.tests.name)
        write_verify(vdir, spec.tests.name, spec.deps, spec.pytest_args)
        for _ in range(runs):
            if not _run_verify(vdir, tmp / "ws"):
                return "baseline-failure"
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _module_rel(spec: MintSpec) -> Path:
    pkg_parts = spec.package.split(".") if spec.package else []
    return Path(*pkg_parts) / spec.module.name if pkg_parts else Path(spec.module.name)


def _write_support(ws: Path, spec: MintSpec) -> None:
    """Copy support modules verbatim into the module's package directory."""
    pkg_dir = ws / _module_rel(spec).parent
    for sup in spec.support:
        if not sup.is_file():
            raise MintError(f"mine: support module {sup} not found")
        (pkg_dir / sup.name).write_text(sup.read_text())


def _write_package_inits(ws: Path, spec: MintSpec) -> None:
    pkg_parts = spec.package.split(".") if spec.package else []
    for i in range(1, len(pkg_parts) + 1):
        init = ws / Path(*pkg_parts[:i]) / "__init__.py"
        if not init.exists():
            init.write_text("")


def mint(spec: MintSpec, out_dir: Path) -> MintResult:
    """Mint one task into out_dir/<spec.name>. The task directory is only
    kept when admitted; a rejected mint leaves nothing behind."""
    t0 = time.monotonic()
    src = spec.module.read_text()
    base = Path(tempfile.mkdtemp(prefix="mine-"))
    triple = {"unmodified_fails": None, "solution_passes": None, "sabotage_fails": None}
    killed = total = 0
    stability: list[bool] = []

    def done(outcome, reason=None, task_dir=None):
        return MintResult(name=spec.name, outcome=outcome, failure_reason=reason,
                          oracle_triple=triple,
                          mutants={"killed": killed, "total": total},
                          stability=stability, task_dir=task_dir,
                          duration_s=int(time.monotonic() - t0))

    try:
        for d in ("workspace", "verify", "solution", "sabotage"):
            (base / d).mkdir(parents=True)
        rel = _module_rel(spec)
        try:
            excised = excise(src, spec.function)
        except (MintError, SyntaxError) as e:
            raise MintError(f"excision failed: {e}") from e
        for d, text in (("workspace", excised), ("solution", src)):
            (base / d / rel).parent.mkdir(parents=True, exist_ok=True)
            (base / d / rel).write_text(text)
        # package importability lives in the workspace (the base every overlay sits on)
        _write_support(base / "workspace", spec)
        _write_package_inits(base / "workspace", spec)
        shutil.copy(spec.tests, base / "verify" / spec.tests.name)
        (base / "prompt.md").write_text(spec.prompt.rstrip() + "\n")
        write_verify(base / "verify", spec.tests.name, spec.deps, spec.pytest_args)

        def variant_passes(*overlay_texts):
            tmp = Path(tempfile.mkdtemp())
            try:
                shutil.copytree(base / "workspace", tmp, dirs_exist_ok=True)
                for text in overlay_texts:
                    (tmp / rel).write_text(text)
                return _run_verify(base / "verify", tmp)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        triple["unmodified_fails"] = not variant_passes()
        if not triple["unmodified_fails"]:
            return done("rejected", "vacuous-task")
        triple["solution_passes"] = variant_passes(src)
        if not triple["solution_passes"]:
            return done("rejected", "solution-fails")

        sabotage_text = None
        for m in mutants(src, spec.function):
            total += 1
            if not variant_passes(m):
                killed += 1
                if sabotage_text is None:
                    sabotage_text = m
        if total == 0:
            return done("rejected", "excision-error")  # no auto-mutant possible
        if sabotage_text is None:
            return done("rejected", "weak-oracle")
        (base / "sabotage" / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / "sabotage" / rel).write_text(sabotage_text)
        triple["sabotage_fails"] = True  # by construction: the kept mutant was killed

        stability = [variant_passes(src) for _ in range(3)]
        if not all(stability):
            return done("rejected", "unstable")

        task_dir = Path(out_dir) / spec.name
        if task_dir.exists():
            raise MintError(f"mine: {task_dir} already exists")
        shutil.copytree(base, task_dir)
        return done("admitted", task_dir=task_dir)
    finally:
        shutil.rmtree(base, ignore_errors=True)
