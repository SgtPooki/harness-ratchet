The `paginate` function in `paginate.py` has at least one bug. Users report that
the last page of results is sometimes empty and that page counts look wrong for
some list sizes. Pages are 1-based, per the docstring.

Find and fix the bug(s) in `paginate.py`. Do not change the function signatures
or the docstrings. You can run `python3 test_smoke.py` to sanity-check, but note
it does not cover every case.
