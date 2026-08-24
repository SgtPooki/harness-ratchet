"""Tiny key=value config loader."""


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
            conf[key.strip()] = value.strip()
    return conf
