"""Fake server startup that computes its retry budget from config."""

from config import load_config


def effective_timeout(conf):
    """Total worst-case wait: timeout per attempt plus backoff between tries."""
    timeout = conf["timeout_seconds"]
    retries = conf["retries"]
    backoff = conf["backoff_seconds"]
    return timeout * retries + backoff * (retries - 1)


def main():
    conf = load_config("settings.conf")
    total = effective_timeout(conf)
    print(f"server starting; worst-case wait {total}s")


if __name__ == "__main__":
    main()
