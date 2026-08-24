"""Tiny key=value config loader."""

_NUMERIC_KEYS = {"timeout_seconds", "retries", "backoff_seconds"}


def load_config(path):
    """Parse a key=value file into a dict.

    Known numeric keys: timeout_seconds, retries, backoff_seconds.
    Unknown keys are kept as strings.
    """
    conf = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key in _NUMERIC_KEYS:
                conf[key] = int(value)
            else:
                conf[key] = value
    return conf
