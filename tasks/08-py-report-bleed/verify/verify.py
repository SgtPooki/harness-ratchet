import subprocess
import sys

ws = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, ws)

from reportlib import build_report  # noqa: E402

# Three sequential reports in one process must be fully isolated.
r1 = build_report("one", [("s1", ["alpha,10", "beta,20"])])
r2 = build_report("two", [("s2", ["gamma,5"])])
r3 = build_report("three", [("s3", ["delta,1", "epsilon,2"])])

assert [r["name"] for r in r1["rows"]] == ["alpha", "beta"], "report 1 rows wrong"
assert [r["name"] for r in r2["rows"]] == ["gamma"], "report 2 leaked rows from report 1"
assert [r["name"] for r in r3["rows"]] == ["delta", "epsilon"], "report 3 leaked rows"
assert r1["total"] == 33.0, f"r1 total {r1['total']}"
assert r2["total"] == 5.5, f"r2 total {r2['total']}"
assert r3["total"] == 3.3, f"r3 total {r3['total']}"

# Dedupe must still work within a single report.
r4 = build_report("four", [("s4", ["x,1", "x,1", "y,2"])])
assert [r["name"] for r in r4["rows"]] == ["x", "y"], "dedupe broken"

# Multi-source report must still aggregate.
r5 = build_report("five", [("s5a", ["a,1"]), ("s5b", ["b,2"])])
assert [r["name"] for r in r5["rows"]] == ["a", "b"], "multi-source aggregation broken"

# The provided repro must now pass.
r = subprocess.run([sys.executable, "repro.py"], cwd=ws, capture_output=True, text=True, timeout=60)
assert r.returncode == 0, f"repro.py still fails: {r.stderr[-300:]}"

print("PASS")
