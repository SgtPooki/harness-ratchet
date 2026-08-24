"""Shared email helpers."""


def normalize_email(email):
    """Strip surrounding whitespace and lowercase the entire address."""
    return email.strip().lower()
