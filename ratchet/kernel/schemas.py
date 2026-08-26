"""Schema loading and validation for the kernel's JSON artifacts."""

import json
from importlib import resources

_SCHEMA_NAMES = ("pack", "task", "admission", "finding")


def load_schema(name: str) -> dict:
    if name not in _SCHEMA_NAMES:
        raise ValueError(f"unknown schema {name!r}; have {_SCHEMA_NAMES}")
    ref = resources.files("ratchet.kernel") / "schemas" / f"{name}.schema.json"
    return json.loads(ref.read_text(encoding="utf-8"))


def validation_errors(name: str, instance) -> list[str]:
    """Validate instance against the named schema; returns human-readable errors."""
    import jsonschema  # deferred so the kernel imports with stdlib only

    validator = jsonschema.Draft202012Validator(load_schema(name))
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(instance), key=str)
    ]
