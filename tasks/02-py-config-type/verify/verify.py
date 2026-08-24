import os
import subprocess
import sys

ws = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, ws)

from config import load_config  # noqa: E402
from server import effective_timeout  # noqa: E402

conf = load_config(os.path.join(ws, "settings.conf"))
# Numeric keys must come back numeric; strings stay strings.
assert conf["service_name"] == "billing-sync", "string keys must stay strings"
assert effective_timeout(conf) == 30 * 3 + 5 * 2, "wrong effective timeout"

# settings.conf must be untouched
raw = open(os.path.join(ws, "settings.conf")).read()
assert "timeout_seconds = 30" in raw and "billing-sync" in raw, "settings.conf was modified"

# server must actually start
r = subprocess.run(
    [sys.executable, "server.py"], cwd=ws, capture_output=True, text=True, timeout=30
)
assert r.returncode == 0, f"server.py failed: {r.stderr[-300:]}"
assert "100" in r.stdout, f"expected worst-case wait 100s in output, got: {r.stdout!r}"

print("PASS")
