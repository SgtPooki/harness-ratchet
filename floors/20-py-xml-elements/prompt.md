`dspy/adapters/xml_adapter.py` is dspy's XML adapter; its `_elements_to_value` function has been removed (it currently raises NotImplementedError). Implement `_elements_to_value` so XML elements convert to Python values consistently with the adapter's parse pipeline and the sibling helpers in this module: leaf text handling, nested element grouping, and repeated-tag list semantics.

Do not change any other function or the docstrings. No new dependencies.
