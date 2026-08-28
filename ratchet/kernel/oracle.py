"""Oracle admission: the mechanical audit that admits a task for scoring.

Port of bin/oracle.sh. The oracle triple: the UNMODIFIED workspace must
FAIL its verifier, workspace + reference solution must PASS, and (where a
sabotage variant exists) workspace + solution + sabotage must FAIL. A task
failing any leg must not be used for scoring.

Sabotage is REQUIRED for minted tasks. The bootstrap tasks minted before
that rule are grandfathered by the kernel-side allowlist below (issue #3,
amended: the list is hardcoded here and never read from pack payload, so a
pack cannot self-declare its way past the sabotage requirement).
"""

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Issue #3 amendment, explicit task ids. 01, 04, 07 carry hand-authored
# sabotage; 09 was minted with sabotage (not grandfathered).
GRANDFATHERED_SABOTAGE = frozenset({
    "02-py-config-type",
    "03-js-slugify",
    "05-py-dedupe",
    "06-py-version-sync",
    "08-py-report-bleed",
})

VERIFY_TIMEOUT_S = 600


@dataclass
class AdmissionResult:
    task_id: str
    unmodified_fails: bool = False
    solution_passes: bool = False
    sabotage: str = "absent"          # present | absent | absent-grandfathered
    sabotage_fails: bool | None = None
    ok: bool = False
    reasons: list[str] = field(default_factory=list)


def _verifier(task_dir: Path) -> tuple[list[str], Path] | None:
    py = task_dir / "verify" / "verify.py"
    mjs = task_dir / "verify" / "verify.mjs"
    if py.is_file():
        return [sys.executable, str(py)], py
    if mjs.is_file():
        return ["node", str(mjs)], mjs
    return None


def run_verifier(task_dir: Path, workspace: Path) -> bool:
    """Run the task's verifier against a workspace copy; True = PASS."""
    cmd = _verifier(task_dir)
    if cmd is None:
        raise FileNotFoundError(f"no verifier found in {task_dir}")
    r = subprocess.run(cmd[0] + [str(workspace)], capture_output=True,
                       timeout=VERIFY_TIMEOUT_S)
    return r.returncode == 0


def run_verifier_capture(task_dir: Path, workspace: Path) -> str:
    """Run the verifier and return its combined output (bin/run.sh semantics:
    stdout+stderr merged; an absent verifier yields empty output)."""
    cmd = _verifier(task_dir)
    if cmd is None:
        return ""
    r = subprocess.run(cmd[0] + [str(workspace)], stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=VERIFY_TIMEOUT_S)
    return r.stdout.decode(errors="replace")


def verifier_passed(verify_output: str) -> bool:
    """The verifier's own verdict, independent of how the agent exited."""
    return any(line == "PASS" for line in verify_output.splitlines())


def composite_pass(verify_output: str, agent_rc: int) -> bool:
    """Composite pass: verifier prints a bare PASS line AND the agent exited 0
    (a timeout that happens to leave a passing tree is not a pass — the mutB
    lesson, ported from bin/run.sh)."""
    return agent_rc == 0 and verifier_passed(verify_output)


def outcome(verifier_pass: bool, agent_rc: int) -> str:
    """The CONTEXT.md four-way rollout outcome (issue #23).

    Descriptive only: composite_pass stays the verdict the gate reads, and
    'overrun' remains a composite failure. Separating it from 'wrong' matters
    because they are different failures with different levers, and collapsing
    them cost this project a wrong diagnosis on a sentinel.
    """
    if verifier_pass:
        return "solved" if agent_rc == 0 else "overrun"
    return "wrong" if agent_rc == 0 else "aborted"


# "11 failed, 13 passed in 140.63s", "24 passed in 3.10s". Verifiers that
# report only PASS or FAIL yield no counts, and that is reported as unknown
# rather than as zero.
_PYTEST_COUNT = re.compile(r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed)\b")


def progress(verify_output: str) -> tuple[int, int] | None:
    """Graded progress as (passed, total) when the verifier reports it (issue #22).

    The composite boolean collapses every degree of wrongness into one zero.
    Where the verifier is pytest the finer signal is already in its output and
    was simply being discarded: a task recorded as 0/4 four times over can be
    hiding a stable 13-of-24 with one clearly worse rollout.
    """
    counts: dict[str, int] = {}
    for n, kind in _PYTEST_COUNT.findall(verify_output or ""):
        kind = "error" if kind.startswith("error") else kind
        counts[kind] = counts.get(kind, 0) + int(n)
    if not counts:
        return None
    total = sum(counts.values())
    if not total:
        return None
    return counts.get("passed", 0) + counts.get("xfailed", 0), total


def admit_task(task_dir: Path) -> AdmissionResult:
    """Run the oracle triple over one task directory."""
    task_dir = Path(task_dir)
    res = AdmissionResult(task_id=task_dir.name)
    if _verifier(task_dir) is None:
        res.reasons.append("no verifier found")
        return res

    tmp = Path(tempfile.mkdtemp(prefix="oracle-"))
    try:
        shutil.copytree(task_dir / "workspace", tmp, dirs_exist_ok=True)
        res.unmodified_fails = not run_verifier(task_dir, tmp)
        if not res.unmodified_fails:
            res.reasons.append("unmodified workspace already passes (task is vacuous)")

        shutil.copytree(task_dir / "solution", tmp, dirs_exist_ok=True)
        res.solution_passes = run_verifier(task_dir, tmp)
        if not res.solution_passes:
            res.reasons.append("reference solution does not pass verifier")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Verifier-robustness check: a deliberately WRONG solution must FAIL.
    if (task_dir / "sabotage").is_dir():
        res.sabotage = "present"
        tmp = Path(tempfile.mkdtemp(prefix="oracle-"))
        try:
            shutil.copytree(task_dir / "workspace", tmp, dirs_exist_ok=True)
            shutil.copytree(task_dir / "solution", tmp, dirs_exist_ok=True)
            shutil.copytree(task_dir / "sabotage", tmp, dirs_exist_ok=True)
            res.sabotage_fails = not run_verifier(task_dir, tmp)
            if not res.sabotage_fails:
                res.reasons.append("sabotaged solution PASSES verifier (verifier is too weak)")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif task_dir.name in GRANDFATHERED_SABOTAGE:
        res.sabotage = "absent-grandfathered"
    else:
        res.sabotage = "absent"
        res.reasons.append("sabotage variant required (task is not grandfathered)")

    res.ok = not res.reasons
    return res
