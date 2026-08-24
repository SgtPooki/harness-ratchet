`concurrency_cap.py` is production middleware whose `dispatch` method has been
removed (it currently raises NotImplementedError). Implement `dispatch` so the
middleware fulfills the contract documented in its docstrings — the module
docstring, the class docstring, and the stub's own docstring together specify
the complete observable behavior.

Do not change any other function, the constants, or the docstrings. Plain
starlette; no new dependencies.
