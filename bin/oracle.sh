#!/bin/bash
# Thin transitional wrapper: the oracle audit lives in the ratchet package
# (ratchet.kernel.oracle, `ratchet audit`). Deleted once every bin/
# workflow is covered by a verb and the step-1 suite is green (issue #2).
set -u
cd "$(dirname "$0")/.."
if command -v ratchet >/dev/null 2>&1; then
  exec ratchet audit --pack tasks "$@"
elif command -v uv >/dev/null 2>&1; then
  exec uv run --project . ratchet audit --pack tasks "$@"
else
  exec python3 -m ratchet.cli audit --pack tasks "$@"
fi
