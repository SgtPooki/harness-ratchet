"""Receipt mailer."""

SENT = []


def _normalize(email):
    return email.lower()


def send_receipt(email):
    """Record a receipt send; returns the normalized recipient."""
    to = _normalize(email)
    SENT.append(to)
    return to
