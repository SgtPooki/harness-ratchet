"""Receipt mailer."""

from emailutil import normalize_email

SENT = []


def send_receipt(email):
    """Record a receipt send; returns the normalized recipient."""
    to = normalize_email(email)
    SENT.append(to)
    return to
