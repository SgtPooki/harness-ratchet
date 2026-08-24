import ast
import os
import sys

ws = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, ws)

import emailutil  # noqa: E402
from mailer import send_receipt  # noqa: E402
from signup import register  # noqa: E402

# Behavior: strip + lowercase whole address, in both call paths and the util.
assert emailutil.normalize_email("  Bob.Smith@Example.COM ") == "bob.smith@example.com"
assert register("  Bob.Smith@Example.COM ") == "bob.smith@example.com"
assert send_receipt(" ALICE@Example.Com  ") == "alice@example.com"
assert register("x+tag@Y.io") == "x+tag@y.io", "plus-tags must be preserved"

# Structure: no private normalization logic left in either module.
for mod in ("signup.py", "mailer.py"):
    tree = ast.parse(open(os.path.join(ws, mod)).read())
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    leftovers = [f for f in funcs if "normal" in f.lower() or "clean" in f.lower()]
    assert not leftovers, f"{mod} still defines its own normalization: {leftovers}"
    src = open(os.path.join(ws, mod)).read()
    assert "emailutil" in src, f"{mod} does not use the shared emailutil module"

print("PASS")
