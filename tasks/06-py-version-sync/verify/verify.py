import os
import re
import sys

ws = sys.argv[1] if len(sys.argv) > 1 else "."


def read(p):
    return open(os.path.join(ws, p)).read()


assert 'version = "2.3.1"' in read("pyproject.toml"), "pyproject version wrong"
assert '__version__ = "2.3.1"' in read("src/payload_tool/__init__.py"), "__init__ version wrong"
conf = read("docs/conf.py")
assert re.search(r'release\s*=\s*"2\.3\.1"', conf), "docs release wrong"
# short X.Y version may stay 2.3

changelog = read("CHANGELOG.md")
assert "## 2.3.1 (current)" in changelog and "## 2.3.0" in changelog, "CHANGELOG.md was modified"

print("PASS")
