`sqlglot/optimizer/qualify_columns.py` is the sqlglot optimizer's column-qualification module; its `_convert_columns_to_dots` function has been removed (it currently raises NotImplementedError). Implement `_convert_columns_to_dots` so it fulfills the contract documented in its docstring: convert Column instances that represent STRUCT or JSON field access into the equivalent Dot expressions, preserving the semantics the module's other passes rely on.

Do not change any other function, the constants, or the docstrings. No new dependencies.
