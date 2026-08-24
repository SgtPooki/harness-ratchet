import os
import re
import shutil
import subprocess
import sys

ws = sys.argv[1] if len(sys.argv) > 1 else "."

# Build fixture tree with hostile-but-legal names.
data = os.path.join(ws, "data")
shutil.rmtree(data, ignore_errors=True)
shutil.rmtree(os.path.join(ws, "backup"), ignore_errors=True)
names = [
    "app.log",
    "with space.log",
    "two  spaces.log",
    "sub dir/nested file.log",
    "sub dir/deep/a-b.log",
    "not-a-log.txt",
    "sub dir/also not.txt",
]
for n in names:
    p = os.path.join(data, n)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write("x: %s\n" % n)

r = subprocess.run(
    ["bash", "backup.sh"], cwd=ws, capture_output=True, text=True, timeout=60
)
assert r.returncode == 0, f"backup.sh exited {r.returncode}: {r.stderr[-300:]}"

backup = os.path.join(ws, "backup")
got = sorted(os.listdir(backup))
logs = [n for n in names if n.endswith(".log")]
assert len(got) == len(logs), f"expected {len(logs)} files, got {len(got)}: {got}"

date_re = re.compile(r"^\d{4}-\d{2}-\d{2}_")
for fn in got:
    assert date_re.match(fn), f"missing/bad date prefix: {fn}"

expected_bases = sorted(os.path.basename(n) for n in logs)
got_bases = sorted(date_re.sub("", fn) for fn in got)
assert got_bases == expected_bases, f"basenames wrong: {got_bases} != {expected_bases}"

# Content must survive the copy.
for fn in got:
    body = open(os.path.join(backup, fn)).read()
    assert body.startswith("x: "), f"content mangled in {fn}"

print("PASS")
