import os, subprocess, sys
ws = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
here = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run(["uv", "run", "--quiet", "--no-project", "--with", "pytest", "--with", "openai>=1.66.2", "--with", "regex", "--with", "orjson", "--with", "tqdm", "--with", "requests", "--with", "pydantic", "--with", "litellm", "--with", "diskcache", "--with", "json-repair", "--with", "tenacity", "--with", "anyio", "--with", "cachetools", "--with", "cloudpickle", "--with", "gepa[dspy]==0.1.4", "--with", "typing-extensions",
     "pytest", "-q", "-p", "no:cacheprovider",
     os.path.join(here, "tests/adapters/test_xml_adapter.py")],
    env=dict(os.environ, PYTHONPATH=ws + os.pathsep + here),
    capture_output=True, text=True, timeout=300)
if r.returncode != 0:
    print(r.stdout[-1500:]); print(r.stderr[-500:]); raise SystemExit(1)
print("PASS")
