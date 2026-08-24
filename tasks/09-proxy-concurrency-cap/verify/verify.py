import os
import subprocess
import sys

ws = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
here = os.path.dirname(os.path.abspath(__file__))

env = dict(os.environ, PYTHONPATH=ws)
r = subprocess.run(
    ["uv", "run", "--quiet", "--no-project",
     "--with", "pytest", "--with", "pytest-asyncio",
     "--with", "httpx", "--with", "starlette",
     "pytest", "-q", "-p", "no:cacheprovider",
     "-o", "asyncio_mode=auto",
     os.path.join(here, "test_concurrency_cap.py")],
    env=env, capture_output=True, text=True, timeout=300,
)
if r.returncode != 0:
    print(r.stdout[-1500:])
    print(r.stderr[-500:])
    raise SystemExit(1)
print("PASS")
