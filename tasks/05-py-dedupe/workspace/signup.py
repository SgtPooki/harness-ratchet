"""Account signup."""

_REGISTERED = set()


def _clean_email(email):
    # lowercase only the domain part
    local, _, domain = email.strip().partition("@")
    return local + "@" + domain.lower()


def register(email):
    """Register an account; returns the normalized email."""
    normalized = _clean_email(email)
    _REGISTERED.add(normalized)
    return normalized
