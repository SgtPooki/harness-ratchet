`sqlglot/optimizer/qualify_columns.py` is the sqlglot optimizer's column-qualification module; its `_qualify_columns` function has been removed (it currently raises NotImplementedError). Implement `_qualify_columns` so it fulfills the contract documented in its docstring: disambiguate every column in scope so each one names its source, using the resolver and the module's helpers, and raising the errors the docstring specifies for ambiguous or unknown columns.

Do not change any other function, the constants, or the docstrings. No new dependencies.
