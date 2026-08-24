"""Account signup."""

from emailutil import normalize_email

_REGISTERED = set()


def register(email):
    """Register an account; returns the normalized email."""
    normalized = normalize_email(email)
    _REGISTERED.add(normalized)
    return normalized
