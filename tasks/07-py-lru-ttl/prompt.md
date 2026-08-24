`ttlcache.py` implements a size-bounded cache with optional per-entry TTL. In
production it evicts the wrong entries under load, and expired entries behave
inconsistently. The docstrings state the intended contract precisely — the
implementation does not honor all of it.

Fix `ttlcache.py` so the implementation matches the documented contract exactly.
Do not change the docstrings or the public API. `python3 test_smoke.py` covers
only the basics.
