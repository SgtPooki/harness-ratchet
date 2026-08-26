import os, subprocess, sys
ws = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
here = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run(["uv", "run", "--quiet", "--no-project", "--with", "pytest", "--with", "duckdb", "--with", "pandas",
     "pytest", "-q", "-p", "no:cacheprovider", "-k", "qualify_columns",
     os.path.join(here, "tests/test_optimizer.py")],
    env=dict(os.environ, PYTHONPATH=ws + os.pathsep + here),
    capture_output=True, text=True, timeout=300)
if r.returncode != 0:
    print(r.stdout[-1500:]); print(r.stderr[-500:]); raise SystemExit(1)
print("PASS")
